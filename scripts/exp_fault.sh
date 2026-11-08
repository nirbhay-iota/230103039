#!/usr/bin/env bash
# Task 3 evidence: FAULT_INJECT=1 makes /parse return 500 {"error": "invalid_model_output"}.
source "$(dirname "$0")/_common.sh"
OUT=results/task3; mkdir -p "$OUT"
kubectl -n $NS set env deploy/parser FAULT_INJECT=1
kubectl -n $NS rollout status deploy/parser --timeout=600s
{
  curl -s -i -X POST "$HOST/parse" -H 'Content-Type: application/json' -d '{"text": "what time is it in tokyo"}'
} | tee "$OUT/fault_inject.txt"
kubectl -n $NS set env deploy/parser FAULT_INJECT=0
kubectl -n $NS rollout status deploy/parser --timeout=600s
