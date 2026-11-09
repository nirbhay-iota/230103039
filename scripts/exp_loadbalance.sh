#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
kubectl -n $NS delete hpa parser --ignore-not-found
kubectl -n $NS scale deploy/parser --replicas=2
wait_ready 2
mkdir -p results
: > "$OUT/lb_top_pods.txt"
start_load loadtest 2m 4
( sleep 30; for _ in 1 2 3 4; do { date -u +%T; kubectl -n $NS top pods; } >> "$OUT/lb_top_pods.txt" 2>&1; sleep 15; done ) &
wait_load
wait
{ load_summary "$OUT/loadtest"; echo "--- per replica / per model version:"; cat "$OUT/loadtest_headers.json"; } | tee "$OUT/lb_summary.txt"
cp "$OUT"/loadtest_stats.csv results/loadtest_stats.csv
cp "$OUT"/loadtest_headers.json results/loadtest_headers.json
kubectl apply -f k8s/app/hpa.yaml
