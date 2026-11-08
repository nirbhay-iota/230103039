#!/usr/bin/env bash
# Task 4.4: show the HPA scaling 1 -> 2 under load and back to 1 afterwards.
source "$(dirname "$0")/_common.sh"
kubectl apply -f k8s/app/hpa.yaml
kubectl -n $NS scale deploy/parser --replicas=1
wait_ready 1
( while true; do echo "$(date -u +%T) $(kubectl -n $NS get hpa parser --no-headers) | ready=$(ready_count)"; sleep 10; done ) \
  > "$OUT/hpa_watch.log" 2>&1 &
watcher=$!
trap 'kill $watcher 2>/dev/null || true' EXIT
start_load hpa 6m 8      # more users than the standard test so that one replica is saturated
wait_load
echo "load finished; waiting for the scale-down (stabilization window 60 s)..."
sleep 150
kubectl -n $NS describe hpa parser > "$OUT/hpa_describe.txt"
kubectl -n $NS top pods > "$OUT/hpa_top_pods.txt" || true
cat "$OUT/hpa_watch.log"
