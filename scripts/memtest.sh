#!/usr/bin/env bash
# Task 3: send 50 requests, one after another, to the container running with 1 CPU and 1 GiB,
# and report the peak memory. Needs the cluster running (object storage) and the image built.
#   scripts/memtest.sh [RUN=v1]
set -euo pipefail
RUN="${1:-v1}"
OUT=results/task3
mkdir -p "$OUT"
scripts/pf.sh start
eval "$(scripts/s3env.sh)"

docker rm -f cc-parser-memtest >/dev/null 2>&1 || true
# --network host lets the container reach the port-forwarded object storage on localhost:8333.
docker run -d --name cc-parser-memtest --network host --cpus=1 --memory=1g --memory-swap=1g \
  -e MODEL_URI="s3://models/${RUN}/" -e MODEL_VERSION="${RUN}" -e S3_ENDPOINT="http://localhost:8333" \
  -e MAX_NEW_TOKENS=96 -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY \
  cc-parser:1.0 >/dev/null
trap 'docker rm -f cc-parser-memtest >/dev/null 2>&1 || true' EXIT

echo "waiting for /readyz ..."
for _ in $(seq 1 180); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/readyz || true)" = "200" ] && break
  sleep 2
done
curl -s -o /dev/null -w 'readyz: %{http_code}\n' localhost:8000/readyz | tee "$OUT/memtest.txt"

: > "$OUT/memtest_stats.txt"
( while true; do docker stats --no-stream --format '{{.MemUsage}} {{.CPUPerc}}' cc-parser-memtest >> "$OUT/memtest_stats.txt" 2>/dev/null || true; sleep 0.5; done ) &
sampler=$!

ok=0
mapfile -t texts < <(python3 -c "
import json
for i, l in enumerate(open('data/validation.jsonl')):
    if i < 50: print(json.loads(l)['text'])")
for t in "${texts[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:8000/parse -H 'Content-Type: application/json' \
         -d "$(python3 -c 'import json,sys;print(json.dumps({"text": sys.argv[1]}))' "$t")")
  [ "$code" = "200" ] && ok=$((ok + 1))
done
kill "$sampler" 2>/dev/null || true

oom=$(docker inspect -f '{{.State.OOMKilled}}' cc-parser-memtest)
peak_cgroup=$(docker exec cc-parser-memtest sh -c 'cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes 2>/dev/null' || echo unknown)
peak_sampled=$(awk '{v=$1; u=v; gsub(/[0-9.]+/,"",u); n=v; gsub(/[A-Za-z]+/,"",n); if(u=="GiB")n*=1024; if(u=="KiB")n/=1024; if(n>m)m=n} END{printf "%.1f MiB", m}' "$OUT/memtest_stats.txt")
{
  echo "requests_ok: ${ok}/50"
  echo "oom_killed: ${oom}"
  echo "peak_memory_sampled_by_docker_stats: ${peak_sampled}"
  echo "peak_memory_cgroup_bytes: ${peak_cgroup}"
  echo "limits: --cpus=1 --memory=1g"
} | tee -a "$OUT/memtest.txt"
docker logs cc-parser-memtest > "$OUT/memtest_container.log" 2>&1 || true
