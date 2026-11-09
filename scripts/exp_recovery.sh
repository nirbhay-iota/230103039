#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
kubectl -n $NS delete hpa parser --ignore-not-found
kubectl -n $NS scale deploy/parser --replicas=2
wait_ready 2
start_load recovery 3m
sleep 20
{
  echo "--- before:"; kubectl -n $NS get pods -l app=parser
  victim=$(kubectl -n $NS get pods -l app=parser -o jsonpath='{.items[0].metadata.name}')
  date -u +"%FT%TZ  deleting pod $victim"
  kubectl -n $NS delete pod "$victim" --wait=false
  sleep 3
  echo "--- right after (a replacement is created):"; kubectl -n $NS get pods -l app=parser
  start=$(date +%s); wait_ready 2
  echo "--- replica count restored to 2 Ready after $(( $(date +%s) - start )) s:"; kubectl -n $NS get pods -l app=parser
} 2>&1 | tee "$OUT/recovery.log"
wait_load
{ echo "--- Locust summary:"; load_summary "$OUT/recovery"; } 2>&1 | tee -a "$OUT/recovery.log"
kubectl apply -f k8s/app/hpa.yaml
