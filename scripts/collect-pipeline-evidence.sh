#!/usr/bin/env bash
# Save evidence for Task 1 (workers ran at the same time, in namespace pipeline, with different shards).
set -euo pipefail
out=results/task1
mkdir -p "$out"
kubectl -n pipeline get job,pods -o wide > "$out/pipeline_pods.txt"
kubectl -n pipeline get pods -l app=teacher-worker \
  -o custom-columns=POD:.metadata.name,START:.status.startTime,INDEX:".metadata.annotations.batch\.kubernetes\.io/job-completion-index" \
  > "$out/pipeline_worker_indexes.txt"
for pod in $(kubectl -n pipeline get pods -l app=teacher-worker -o name); do
  kubectl -n pipeline logs "$pod" > "$out/$(basename "$pod").log"
done
kubectl get ns data pipeline app > "$out/namespaces.txt"
kubectl -n data get statefulset,pods,svc > "$out/seaweedfs.txt"
echo "evidence written to $out/"
