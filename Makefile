SHELL := /bin/bash
CLUSTER := cc-mini
VENV := .venv
PY := $(VENV)/bin/python
PYTHON ?= python3.11
PDF_ENGINE ?= tectonic
RUN ?= v1
SUBSET ?=
S3 = eval "$$(scripts/s3env.sh)" && $(PY) scripts/s3_tool.py

.DEFAULT_GOAL := help
.PHONY: help up down setup setup-train cluster namespaces secrets storage buckets seed-storage \
        image-worker image-app images label verify-shards clean-data fetch-shards fetch-train task1-evidence \
        train package upload-model release restore-models eval-teacher eval-baseline eval-student \
        deploy-app test lint loadtest scan

help:
	@echo "make up      build and deploy the whole system on a local k3d cluster (from a fresh clone)"
	@echo "make down    delete the cluster"
	@echo "make test    unit tests;  make lint  ruff;  make train [RUN=v2] [SUBSET=50]"
	@echo "see README.md for the full list"

# ---------------------------------------------------------------------------------------------
# The whole system in one command. Needs: docker, k3d, kubectl, python3, curl, openssl.
# Object storage is filled from files in this repository (dataset, teacher shards) and from the
# model GitHub Releases model-v1 / model-v2 (weights are never stored in Git).
# ---------------------------------------------------------------------------------------------
up:
	$(MAKE) cluster
	$(MAKE) seed-storage
	$(MAKE) images
	$(MAKE) restore-models
	$(MAKE) deploy-app
	@echo "ready: curl -s -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{\"text\": \"what is the weather in london\"}'"

# Deletes the whole cluster (and with it every namespace, volume and secret).
down:
	-scripts/pf.sh stop
	k3d cluster delete $(CLUSTER)

# ---- host Python environments ----
$(PY): requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q -r requirements-dev.txt
	@touch $(PY)

setup: $(PY)

# CPU-only PyTorch and Transformers, installed once into the same virtual environment.
$(VENV)/.train-ready: $(PY) requirements-train.txt
	$(PY) -m pip install -q -r requirements-train.txt
	@touch $@

setup-train: $(VENV)/.train-ready

# ---- Task 1: cluster, object storage, buckets ----
cluster:
	k3d cluster list $(CLUSTER) >/dev/null 2>&1 || k3d cluster create --config cluster/k3d.yaml
	kubectl config use-context k3d-$(CLUSTER)
	kubectl wait --for=condition=Ready node --all --timeout=120s

namespaces:
	kubectl apply -f k8s/00-namespaces.yaml

secrets: namespaces
	scripts/gen-secrets.sh

storage: secrets
	kubectl apply -f k8s/data/seaweedfs.yaml
	kubectl -n data rollout status statefulset/seaweedfs --timeout=300s

buckets: storage $(PY)
	scripts/pf.sh start
	$(S3) mb datasets models

# Fill the buckets from files in the repository.
seed-storage: buckets
	$(S3) put data/commands_pool.jsonl datasets commands_pool.jsonl
	@if ls data/teacher/shard-*.jsonl >/dev/null 2>&1; then \
	  for f in data/teacher/shard-*.jsonl; do $(S3) put $$f datasets teacher/$$(basename $$f); done; fi
	@if [ -f data/v1/train.jsonl ]; then \
	  $(S3) put data/v1/train.jsonl datasets v1/train.jsonl && $(S3) put data/v1/train.sha256 datasets v1/train.sha256; fi

image-worker:
	docker build -f worker/Dockerfile -t cc-worker:1.0 .
	k3d image import cc-worker:1.0 -c $(CLUSTER)

image-app:
	docker build -f service/Dockerfile -t cc-parser:1.0 .
	k3d image import cc-parser:1.0 -c $(CLUSTER)

images: image-worker image-app

# Teacher labelling: two parallel workers in namespace pipeline. Ollama must be running on the host,
# listening on 0.0.0.0, with the model pulled (ollama pull phi3.5).
label: buckets image-worker
	$(S3) put data/commands_pool.jsonl datasets commands_pool.jsonl
	kubectl apply -f k8s/pipeline/teacher-job.yaml
	kubectl -n pipeline wait --for=condition=complete job/teacher-labelling --timeout=24h

verify-shards: $(PY)
	scripts/pf.sh start
	eval "$$(scripts/s3env.sh)" && $(PY) worker/verify_shards.py --pool data/commands_pool.jsonl --shard-count 2

clean-data: $(PY)
	scripts/pf.sh start
	mkdir -p results
	eval "$$(scripts/s3env.sh)" && $(PY) worker/clean.py --counts-out results/clean_counts.json

# Keep a copy of the shard outputs in the repository so the cleaning step can be reproduced anywhere.
fetch-shards: $(PY)
	scripts/pf.sh start
	mkdir -p data/teacher
	for i in 0 1; do $(S3) get datasets teacher/shard-$$i.jsonl data/teacher/shard-$$i.jsonl; done

task1-evidence:
	scripts/collect-pipeline-evidence.sh

# ---- Task 2: training, packaging, evaluation ----
# Copy the cleaned dataset (and its checksum) from object storage into the repository.
fetch-train: $(PY)
	scripts/pf.sh start
	mkdir -p data/v1
	$(S3) get datasets v1/train.jsonl data/v1/train.jsonl
	$(S3) get datasets v1/train.sha256 data/v1/train.sha256
	cd data/v1 && shasum -a 256 -c train.sha256

# One command, reads only training/config.yaml:  make train | make train RUN=v2 | make train SUBSET=50
train: $(VENV)/.train-ready
	$(PY) training/train.py --config training/config.yaml --run $(RUN) $(if $(SUBSET),--subset $(SUBSET),)

package:
	$(PY) training/package.py --run $(RUN)

# Model and tokenizer -> bucket models under v1/ or v2/ (s3://models/<RUN>/), including model.sha256.
upload-model: package
	scripts/pf.sh start
	$(S3) put-dir artifacts/$(RUN) models $(RUN)

# Publish the archive and its checksum as GitHub Release assets (needs `gh auth login`).
release: package
	gh release create model-$(RUN) artifacts/model-$(RUN).tar.gz artifacts/model-$(RUN).sha256 \
	  --title "Model $(RUN)" --notes "Pythia-70M student distilled from phi3.5 (see version.json inside the archive)." \
	  || gh release upload model-$(RUN) artifacts/model-$(RUN).tar.gz artifacts/model-$(RUN).sha256 --clobber

restore-models: $(PY)
	scripts/restore-model.sh v1
	scripts/restore-model.sh v2

# Validation scores for the three models (raw outputs and reports are kept in results/).
eval-teacher:
	$(PY) training/eval_teacher.py --output results/teacher_validation_predictions.jsonl
	$(PY) tools/score.py results/teacher_validation_predictions.jsonl data/validation.jsonl --out results/teacher_validation.json

eval-baseline: $(VENV)/.train-ready
	$(PY) training/evaluate.py --model EleutherAI/pythia-70m --output results/baseline_validation_predictions.jsonl
	$(PY) tools/score.py results/baseline_validation_predictions.jsonl data/validation.jsonl --out results/baseline_validation.json

eval-student: $(VENV)/.train-ready
	$(PY) training/evaluate.py --model artifacts/$(RUN) --output results/student_$(RUN)_validation_predictions.jsonl
	$(PY) tools/score.py results/student_$(RUN)_validation_predictions.jsonl data/validation.jsonl --out results/student_$(RUN)_validation.json

# ---- Tasks 3-4: deploy the service ----
deploy-app:
	kubectl apply -f k8s/app/deployment.yaml -f k8s/app/service.yaml -f k8s/app/ingress.yaml -f k8s/app/hpa.yaml
	kubectl -n app rollout status deployment/parser --timeout=600s

# ---- Task 6: checks ----
test: $(PY)
	$(PY) -m pytest -q tests

lint: $(PY)
	$(PY) -m ruff check .

scan:
	gitleaks detect --source . --no-banner --redact

# ---- Task 7: standard load test (see scripts/ for the Task 4 experiments) ----
loadtest: $(PY)
	mkdir -p results
	$(VENV)/bin/locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
	  --host http://localhost:8080 --csv results/loadtest

# ---- Report (needs pandoc and a LaTeX engine) ----
report:
	pandoc report/report.md -o report/report.pdf --pdf-engine=$(PDF_ENGINE)

.PHONY: report
