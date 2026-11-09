#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
kubectl -n $NS delete hpa parser --ignore-not-found
kubectl -n $NS scale deploy/parser --replicas=2
wait_ready 2
start_load rolling 4m
sleep 20
{
  date -u +"%FT%TZ  update: MODEL_VERSION=v2 MODEL_URI=s3://models/v2/"
  kubectl -n $NS set env deploy/parser MODEL_VERSION=v2 MODEL_URI=s3://models/v2/
  kubectl -n $NS rollout status deploy/parser --timeout=600s
  date -u +"%FT%TZ  update finished"
  sleep 20
  date -u +"%FT%TZ  rollback: kubectl rollout undo"
  kubectl -n $NS rollout undo deploy/parser
  kubectl -n $NS rollout status deploy/parser --timeout=600s
  date -u +"%FT%TZ  rollback finished"
} 2>&1 | tee "$OUT/rolling_update.log"
wait_load
{
  echo "--- X-Model-Version after rollback:"
  curl -s -D - -o /dev/null -X POST "$HOST/parse" -H 'Content-Type: application/json' -d '{"text": "what time is it in tokyo"}' | grep -i -E '^(HTTP|x-model-version|x-served-by)'
  echo "--- Locust summary:"
  load_summary "$OUT/rolling"
  echo "--- served per model version during the run:"
  cat "$OUT/rolling_headers.json"
  kubectl -n $NS rollout history deploy/parser
} 2>&1 | tee -a "$OUT/rolling_update.log"
kubectl apply -f k8s/app/hpa.yaml
