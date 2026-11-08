SHELL := /bin/bash
CLUSTER := cc-mini
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: setup cluster namespaces secrets storage buckets upload-data down \
        image-worker label verify-shards clean-data task1-evidence \
        setup-train fetch-train train package upload-model release eval-teacher eval-baseline eval-student

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

# ---- Task 2: training, packaging, evaluation ----
RUN ?= v1
SUBSET ?=

setup-train:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -r requirements-dev.txt -r requirements-train.txt

# Copy the cleaned dataset (and its checksum) from object storage into the repository.
fetch-train:
	scripts/pf.sh start
	mkdir -p data/v1
	eval "$$(scripts/s3env.sh)" && $(PY) scripts/s3_tool.py get datasets v1/train.jsonl data/v1/train.jsonl \
	  && $(PY) scripts/s3_tool.py get datasets v1/train.sha256 data/v1/train.sha256
	cd data/v1 && sha256sum -c train.sha256

# One command, reads only training/config.yaml:  make train   |   make train RUN=v2   |   make train SUBSET=50
train:
	$(PY) training/train.py --config training/config.yaml --run $(RUN) $(if $(SUBSET),--subset $(SUBSET),)

package:
	$(PY) training/package.py --run $(RUN)

# Model and tokenizer -> bucket models under models/<RUN>/ (including model.sha256).
upload-model: package
	scripts/pf.sh start
	eval "$$(scripts/s3env.sh)" && $(PY) scripts/s3_tool.py put-dir artifacts/$(RUN) models models/$(RUN)

# Publish the archive and its checksum as GitHub Release assets (needs `gh auth login`).
release: package
	gh release create model-$(RUN) artifacts/model-$(RUN).tar.gz artifacts/model-$(RUN).sha256 \
	  --title "Model $(RUN)" --notes "Pythia-70M student distilled from phi3.5 (see version.json inside the archive)." \
	  || gh release upload model-$(RUN) artifacts/model-$(RUN).tar.gz artifacts/model-$(RUN).sha256 --clobber

# Validation scores for the three models (raw outputs and reports are kept in results/).
eval-teacher:
	$(PY) training/eval_teacher.py --output results/teacher_validation_predictions.jsonl
	$(PY) tools/score.py results/teacher_validation_predictions.jsonl data/validation.jsonl --out results/teacher_validation.json

eval-baseline:
	$(PY) training/evaluate.py --model EleutherAI/pythia-70m --output results/baseline_validation_predictions.jsonl
	$(PY) tools/score.py results/baseline_validation_predictions.jsonl data/validation.jsonl --out results/baseline_validation.json

eval-student:
	$(PY) training/evaluate.py --model artifacts/$(RUN) --output results/student_$(RUN)_validation_predictions.jsonl
	$(PY) tools/score.py results/student_$(RUN)_validation_predictions.jsonl data/validation.jsonl --out results/student_$(RUN)_validation.json

# Deletes the whole cluster (and with it every namespace, volume and secret).
down:
	scripts/pf.sh stop
	k3d cluster delete $(CLUSTER)
