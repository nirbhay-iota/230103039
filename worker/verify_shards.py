"""Check that every command id of commands_pool.jsonl appears in exactly one shard output.

  python verify_shards.py --pool data/commands_pool.jsonl --shard-count 2 --local-dir shards/
  python verify_shards.py --pool data/commands_pool.jsonl --shard-count 2          # object storage

Also checks that each shard holds exactly the ids its SHARD_INDEX should have labelled
(line number % SHARD_COUNT == shard index). Exits with status 1 on any gap, repeat or misplaced id.
"""
import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from worker import shard_records  # noqa: E402


def verify(pool_lines, shards, shard_count):
    """shards: {shard_index: [records]}. Returns a list of problem strings (empty = fine)."""
    problems = []
    seen = collections.Counter()
    for idx, records in shards.items():
        expected = {rec["id"] for _, rec in shard_records(pool_lines, idx, shard_count)}
        got = [r["id"] for r in records]
        for i in got:
            seen[i] += 1
        wrong = sorted(set(got) - expected)
        if wrong:
            problems.append(f"shard {idx} holds ids that belong to another shard: {wrong[:5]}")
    pool_ids = [json.loads(line)["id"] for line in pool_lines if line.strip()]
    missing = [i for i in pool_ids if seen[i] == 0]
    repeated = sorted(i for i, n in seen.items() if n > 1)
    if missing:
        problems.append(f"{len(missing)} ids are missing, e.g. {missing[:5]}")
    if repeated:
        problems.append(f"{len(repeated)} ids appear more than once, e.g. {repeated[:5]}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pool", default="data/commands_pool.jsonl")
    ap.add_argument("--shard-count", type=int, required=True)
    ap.add_argument("--local-dir")
    a = ap.parse_args()
    pool_lines = pathlib.Path(a.pool).read_text(encoding="utf-8").splitlines()
    shards = {}
    if a.local_dir:
        for i in range(a.shard_count):
            p = pathlib.Path(a.local_dir) / f"shard-{i}.jsonl"
            shards[i] = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    else:
        from clean import s3_client
        s3 = s3_client()
        for i in range(a.shard_count):
            body = s3.get_object(Bucket="datasets", Key=f"teacher/shard-{i}.jsonl")["Body"].read().decode("utf-8")
            shards[i] = [json.loads(x) for x in body.splitlines() if x.strip()]
    problems = verify(pool_lines, shards, a.shard_count)
    total = sum(len(v) for v in shards.values())
    print(f"{total} shard records across {len(shards)} shards; pool has {len([x for x in pool_lines if x.strip()])} commands")
    if problems:
        print("\n".join("PROBLEM: " + p for p in problems))
        sys.exit(1)
    print("OK: every command id appears in exactly one shard output")


if __name__ == "__main__":
    main()
