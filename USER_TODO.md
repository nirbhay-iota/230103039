# What you still have to do yourself

## Current progress — 9 November 2026

Model work stopped at the user's request. Docker is stopped and the Ollama model/server were stopped;
the Job suspension could not be confirmed because the Kubernetes API was unavailable. Do not restart model
work without a new request. Installed tools, Python setup, 36 unit tests, lint and the earlier secret scan
are complete. Portability fixes are in commit `2df127b`. See `results/current_results.md` for the actual results:
250 locally saved raw replies, 112 retained after offline cleaning, 6/6 NACL sample checks, and a hypothetical
INR 7.90/hour for two configured replicas. These are partial results. Training, model releases, validation,
service experiments, CI runs, and submission remain pending.

The code, manifests, scripts, CI, docs and the whole of Task 5 are written. What is left needs your laptop
(Docker, k3d, Ollama, PyTorch) or your accounts. **Some setup and partial-data evidence now exists in `results/`:
do not write numbers into the report that did not come from a run.** Delete this file before the final tag if you like.

## 0. Once
- [ ] Install Docker, k3d, kubectl, Ollama, GitHub CLI (`gh auth login`), Python 3.11+, make. Give Docker >= 6 GB RAM.
- [ ] `ollama pull phi3.5`, then run the server as `OLLAMA_HOST=0.0.0.0 ollama serve` (Pods reach it via `host.k3d.internal`).
- [x] Check the repository name: you typed `230203039` but the repository that exists is `230103039`.
- [x] `make setup`

## 1. Task 1: labelling (start early; hours on CPU)
- [ ] `make cluster seed-storage image-worker` (not `make up`: the model Releases do not exist yet)
- [ ] `make label` (two workers in namespace `pipeline`); watch with `kubectl -n pipeline logs -f -l app=teacher-worker --prefix`
- [ ] `make task1-evidence` (pods, shard indexes, logs -> `results/task1/`)
- [ ] `make verify-shards` (every id in exactly one shard), then `make clean-data` (counts -> `results/clean_counts.json`)
- [ ] `make fetch-shards fetch-train`, then commit `data/teacher/`, `data/v1/`, `results/` ("make up" and the graders use these)
- [ ] Skim some `teacher_raw` replies. Do not edit them.

## 2. Task 2: training and models
- [ ] `make train SUBSET=50` (must finish), then `make train` (v1) and `make train RUN=v2`; commit `training/loss.csv`
- [ ] `make upload-model RUN=v1`, `make upload-model RUN=v2`
- [ ] `make release RUN=v1`, `make release RUN=v2` (Release assets + checksums; check `artifacts/model-v1.sha256` equals the bucket's `models/v1/model.sha256`)
- [ ] `make eval-teacher eval-baseline eval-student` and `make eval-student RUN=v2`; commit `results/`
- [ ] If validity is low, change the settings in `training/config.yaml` (epochs, learning rate), retrain, and say so in the report.
      The hidden test needs JSON validity >= 95%.

## 3. Tasks 3-4: service and cluster
- [ ] `make image-app` (check `docker image ls cc-parser:1.0` is <= 2 GB), `make deploy-app` (or `make up` now that Releases exist)
- [ ] `scripts/memtest.sh v1` (50 requests at 1 CPU / 1 GiB; peak memory in `results/task3/memtest.txt`)
- [ ] `scripts/exp_fault.sh`, `scripts/exp_notready.sh`
- [ ] `scripts/exp_hpa.sh`, `exp_rolling_update.sh`, `exp_recovery.sh`, `exp_coldstart.sh`, `exp_loadbalance.sh`
      (each saves its output in `results/task4/`; the load balancing one also saves the standard load test used in Task 7)

## 4. Task 7 and CI
- [ ] `python scripts/cost_slo.py --stats results/loadtest_stats.csv` -> `results/cost_slo.md`
- [ ] Push to GitHub. In the Actions tab run **ci** with `model_source = release` (must pass) and again with `baseline` (must fail at the quality gate).
      Copy both run links into the report.
- [ ] `make scan` (gitleaks) locally and check the CI secret-scan job is green.

## 5. Report and submission
- [ ] Fill every `[[MEASURE...]]` in `report/report.md` (`python scripts/check_report.py`), your name and roll number, and the Task 2 discussion/suitability text in your own words
- [ ] `make report` -> `report/report.pdf` (max 8 pages without references/appendices); commit it
- [ ] Complete the checklist in `AI_USE.md` honestly
- [ ] **Handwritten reflection** (3 pages, scanned, with your GitHub link, name and roll number), saved as `<roll_number>.pdf` exactly
- [ ] Commit, `git tag final`, `git push origin main --tags` before the deadline

## Things I could not test (tell me if they fail)
The sandbox had no Docker daemon, k3d, kubectl, Ollama or PyTorch, so these were checked by reading, not running:
SeaweedFS flags and S3 credentials, the Dockerfile pins (`service/requirements.txt`), the Ingress, HPA metrics, `host.k3d.internal`
from Pods, the training hyper-parameters, the 1 GiB memory fit, and the API tests (`tests/test_api.py` is skipped where FastAPI is missing; CI runs it).
The unit tests, the NACL simulator and the cleaning, sharding, packaging and cost logic were run.
