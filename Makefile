SHELL := /bin/bash
CLUSTER := cc-mini
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup cluster namespaces secrets storage buckets upload-data down \
        image-worker label verify-shards clean-data task1-evidence

# Host Python environment (boto3, locust, pytest, ruff).
setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r requirements-dev.txt

# ---- Task 1: cluster, object storage, buckets ----
cluster:
	k3d cluster list $(CLUSTER) >/dev/null 2>&1 || k3d cluster create --config cluster/k3d.yaml
	kubectl config use-context k3d-$(CLUSTER)

namespaces:
	kubectl apply -f k8s/00-namespaces.yaml

secrets: namespaces
	scripts/gen-secrets.sh

storage: secrets
	kubectl apply -f k8s/data/seaweedfs.yaml
	kubectl -n data rollout status statefulset/seaweedfs --timeout=240s

buckets: storage
	scripts/pf.sh start
	eval "$$(scripts/s3env.sh)" && $(PY) scripts/s3_tool.py mb datasets models

upload-data: buckets
	eval "$$(scripts/s3env.sh)" && $(PY) scripts/s3_tool.py put data/commands_pool.jsonl datasets commands_pool.jsonl

# Teacher labelling: two parallel workers in namespace pipeline (Ollama must be running on the host,
# listening on 0.0.0.0, with the model pulled:  ollama pull phi3.5).
image-worker:
	docker build -f worker/Dockerfile -t cc-worker:1.0 .
	k3d image import cc-worker:1.0 -c $(CLUSTER)

label: upload-data image-worker
	kubectl apply -f k8s/pipeline/teacher-job.yaml
	kubectl -n pipeline wait --for=condition=complete job/teacher-labelling --timeout=24h

verify-shards:
	scripts/pf.sh start
	eval "$$(scripts/s3env.sh)" && $(PY) worker/verify_shards.py --pool data/commands_pool.jsonl --shard-count 2

clean-data:
	scripts/pf.sh start
	mkdir -p results
	eval "$$(scripts/s3env.sh)" && $(PY) worker/clean.py --counts-out results/clean_counts.json

task1-evidence:
	scripts/collect-pipeline-evidence.sh

# Deletes the whole cluster (and with it every namespace, volume and secret).
down:
	scripts/pf.sh stop
	k3d cluster delete $(CLUSTER)
