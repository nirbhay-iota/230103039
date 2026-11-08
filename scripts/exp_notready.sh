#!/usr/bin/env bash
# Task 4.2 evidence: while the model is still loading, the Service has no ready endpoints.
source "$(dirname "$0")/_common.sh"
kubectl -n $NS delete hpa parser --ignore-not-found
kubectl -n $NS scale deploy/parser --replicas=0
sleep 5
kubectl -n $NS scale deploy/parser --replicas=1
{
  for _ in $(seq 1 12); do
    echo "$(date -u +%T) endpoints: $(kubectl -n $NS get endpoints parser -o jsonpath='{.subsets[*].addresses[*].ip}')|notready: $(kubectl -n $NS get endpoints parser -o jsonpath='{.subsets[*].notReadyAddresses[*].ip}') | $(kubectl -n $NS get pods -l app=parser --no-headers)"
    sleep 3
  done
} | tee "$OUT/notready_endpoints.log"
wait_ready 1
echo "$(date -u +%T) after loading: endpoints: $(kubectl -n $NS get endpoints parser -o jsonpath='{.subsets[*].addresses[*].ip}')" | tee -a "$OUT/notready_endpoints.log"
kubectl -n $NS scale deploy/parser --replicas=2
kubectl apply -f k8s/app/hpa.yaml
