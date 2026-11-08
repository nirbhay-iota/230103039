"""Clean the teacher's shard outputs and write the training set (Task 1, step 6).

Reads every datasets/teacher/shard-*.jsonl, drops the bad records, and writes
    datasets/v1/train.jsonl     records in id order
    datasets/v1/train.sha256    SHA-256 of train.jsonl, in `sha256sum` format
The same input always produces byte-identical output, so the checksum is reproducible.

A record is rejected for the FIRST reason that applies, so every input record falls in exactly one
class and   input = (a) + (b) + (c) + (d) + duplicates + kept :
  (a) the teacher reply is not valid JSON
  (b) the reply is not an object with exactly the keys intent, date, time, place
  (c) the intent is not one of the eight
  (d) a slot value is neither null nor non-empty text that appears in the command
  (e) duplicates: among records that passed (a)-(d), a command whose text was already seen with a
      smaller id (the record with the smallest id is kept)

Usage
  python clean.py                                  # read and write object storage (S3_ENDPOINT + AWS_* variables)
  python clean.py --local-dir shards/ --out-dir out/   # same logic on local files (used by the tests)
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys

KEYS = ("intent", "date", "time", "place")
SLOTS = ("date", "time", "place")
REASONS = ("a_invalid_json", "b_bad_keys", "c_bad_intent", "d_bad_slot")


def load_intents(schema_path):
    with open(schema_path, encoding="utf-8") as f:
        return set(json.load(f)["intents"])


def classify(record, intents):
    """Return the rejection reason for one record, or None if it is acceptable."""
    try:
        obj = json.loads(record["teacher_raw"].strip())
    except (json.JSONDecodeError, AttributeError, KeyError):
        return "a_invalid_json"
    if not isinstance(obj, dict) or set(obj.keys()) != set(KEYS):
        return "b_bad_keys"
    if not isinstance(obj["intent"], str) or obj["intent"] not in intents:
        return "c_bad_intent"
    command = record["text"].lower()
    for slot in SLOTS:
        value = obj[slot]
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or value.lower() not in command:
            return "d_bad_slot"
    return None


def clean(records, intents):
    """Return (kept_records_sorted_by_id, counts)."""
    counts = {"input_records": len(records), **{r: 0 for r in REASONS}, "duplicates": 0, "kept": 0}
    valid = []
    for rec in records:
        reason = classify(rec, intents)
        if reason:
            counts[reason] += 1
        else:
            valid.append(rec)
    kept, seen = [], set()
    for rec in sorted(valid, key=lambda r: r["id"]):
        if rec["text"] in seen:
            counts["duplicates"] += 1
            continue
        seen.add(rec["text"])
        kept.append(rec)
    counts["kept"] = len(kept)
    assert counts["input_records"] == sum(counts[k] for k in (*REASONS, "duplicates", "kept"))
    return kept, counts


def encode(kept):
    return "".join(
        json.dumps({"id": r["id"], "text": r["text"], "teacher_raw": r["teacher_raw"]}, ensure_ascii=False) + "\n"
        for r in kept
    ).encode("utf-8")


def parse_lines(blob, source):
    out = []
    for n, line in enumerate(blob.decode("utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                sys.exit(f"{source}: line {n} is not valid JSON (the shard file itself is damaged)")
    return out


def check_ids(records):
    ids = [r["id"] for r in records]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        sys.exit(f"the same id appears in more than one shard record: {dup[:5]} ...")


def read_local(folder):
    records = []
    for p in sorted(pathlib.Path(folder).glob("shard-*.jsonl")):
        records += parse_lines(p.read_bytes(), str(p))
    return records


def s3_client():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}))


def read_s3(s3, bucket, prefix):
    records = []
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", [])]
    for key in sorted(k for k in keys if k.rsplit("/", 1)[-1].startswith("shard-") and k.endswith(".jsonl")):
        records += parse_lines(s3.get_object(Bucket=bucket, Key=key)["Body"].read(), key)
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local-dir", help="read shard files from this folder instead of object storage")
    ap.add_argument("--out-dir", help="with --local-dir: write train.jsonl and train.sha256 here")
    ap.add_argument("--bucket", default="datasets")
    ap.add_argument("--shard-prefix", default="teacher/")
    ap.add_argument("--out-prefix", default="v1/")
    ap.add_argument("--schema", default=None)
    ap.add_argument("--counts-out", default=None, help="also write the counts as JSON to this file")
    a = ap.parse_args()

    here = pathlib.Path(__file__).resolve().parent
    schema = a.schema or next(str(p) for p in (here / "schema.json", here.parent / "data" / "schema.json") if p.exists())
    intents = load_intents(schema)

    s3 = None
    if a.local_dir:
        records = read_local(a.local_dir)
    else:
        s3 = s3_client()
        records = read_s3(s3, a.bucket, a.shard_prefix)
    check_ids(records)

    kept, counts = clean(records, intents)
    blob = encode(kept)
    digest = hashlib.sha256(blob).hexdigest()
    checksum_line = f"{digest}  train.jsonl\n".encode()

    if a.local_dir:
        out = pathlib.Path(a.out_dir or ".")
        out.mkdir(parents=True, exist_ok=True)
        (out / "train.jsonl").write_bytes(blob)
        (out / "train.sha256").write_bytes(checksum_line)
        where = str(out)
    else:
        prefix = a.out_prefix.rstrip("/") + "/"
        s3.put_object(Bucket=a.bucket, Key=prefix + "train.jsonl", Body=blob)
        s3.put_object(Bucket=a.bucket, Key=prefix + "train.sha256", Body=checksum_line)
        where = f"s3://{a.bucket}/{prefix}"

    print(json.dumps(counts, indent=2))
    print(f"sha256 {digest}\nwritten to {where}")
    if a.counts_out:
        with open(a.counts_out, "w", encoding="utf-8") as f:
            json.dump({**counts, "sha256": digest}, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
