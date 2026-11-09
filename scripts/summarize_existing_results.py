#!/usr/bin/env python3
"""Summarize saved teacher shards offline; never call a model or the cluster."""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))
from clean import clean, encode, load_intents, read_local  # noqa: E402
from verify_shards import verify  # noqa: E402


def main():
    paths = sorted((ROOT / "data/teacher").glob("shard-*.jsonl"))
    if not paths:
        raise SystemExit("No saved teacher shards; no results calculated.")
    rows = read_local(ROOT / "data/teacher")
    kept, counts = clean(rows, load_intents(ROOT / "data/schema.json"))
    pool = (ROOT / "data/commands_pool.jsonl").read_text().splitlines()
    pool_count = sum(bool(line.strip()) for line in pool)
    shards = {int(p.stem.split("-")[-1]): [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
              for p in paths}
    problems = verify(pool, shards, 2)
    blob = encode(kept)
    digest = hashlib.sha256(blob).hexdigest()
    card = json.loads((ROOT / "data/rate_card.json").read_text())
    per_replica = card["vcpu_hour"] + card["gib_memory_hour"]
    summary = {
        "scope": "partial locally saved shards; not the complete labelling run or validation set",
        "pool_records": pool_count,
        "saved_records": len(rows),
        "coverage_percent": 100 * len(rows) / pool_count,
        "json_parseable_records": counts["input_records"] - counts["a_invalid_json"],
        "json_parseable_percent": 100 * (len(rows) - counts["a_invalid_json"]) / len(rows),
        "retained_percent": 100 * len(kept) / len(rows),
        "counts": counts,
        "partial_clean_sha256": digest,
        "shard_verification_problems": problems,
        "sources": [{"path": str(p.relative_to(ROOT)), "records": len(shards[int(p.stem.split('-')[-1])]),
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
        "cost_assumptions": {"currency": card["currency"], "replicas": 2, "cpu_limit_per_replica": 1,
                             "memory_limit_gib_per_replica": 1, "hourly_per_replica": per_replica,
                             "hourly_two_replicas": 2 * per_replica},
    }
    out = ROOT / "results/partial"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "train.jsonl").write_bytes(blob)
    (out / "train.sha256").write_text(f"{digest}  train.jsonl\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
