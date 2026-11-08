#!/usr/bin/env bash
# Task 4.7: delete all Pods three times; report Pod-creation-to-Ready time and the download log lines.
source "$(dirname "$0")/_common.sh"
kubectl -n $NS delete hpa parser --ignore-not-found
kubectl -n $NS scale deploy/parser --replicas=2
wait_ready 2
: > "$OUT/coldstart_times.txt"
for run in 1 2 3; do
  kubectl -n $NS delete pods -l app=parser --wait=true
  wait_ready 2
  kubectl -n $NS get pods -l app=parser -o json | python3 -c '
import json, sys
from datetime import datetime
def t(s): return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
for p in json.load(sys.stdin)["items"]:
    ready = next(c["lastTransitionTime"] for c in p["status"]["conditions"] if c["type"] == "Ready")
    print(p["metadata"]["name"], int((t(ready) - t(p["metadata"]["creationTimestamp"])).total_seconds()))
' | sed "s/^/run${run} /" | tee -a "$OUT/coldstart_times.txt"
  for pod in $(kubectl -n $NS get pods -l app=parser -o name); do
    echo "=== run${run} ${pod}" >> "$OUT/coldstart_logs.txt"
    kubectl -n $NS logs "$pod" | grep -E "downloading model|downloaded|model .* ready" >> "$OUT/coldstart_logs.txt"
  done
done
python3 - "$OUT/coldstart_times.txt" <<'PY' | tee "$OUT/coldstart_summary.txt"
import statistics, sys
rows = [l.split() for l in open(sys.argv[1]) if l.strip()]
per_run = {}
for run, _pod, secs in rows:
    per_run.setdefault(run, []).append(int(secs))
# One cold-start time per run: the slowest of the two Pods (when the whole service is back).
times = [max(v) for _, v in sorted(per_run.items())]
print("cold-start time per run (slowest Pod, seconds):", times)
print("median of three runs (seconds):", statistics.median(times))
print("median over all individual Pods (seconds):", statistics.median(int(r[2]) for r in rows))
PY
kubectl apply -f k8s/app/hpa.yaml
