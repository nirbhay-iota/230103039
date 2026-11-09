# Cloud Computing mini project: distilling and deploying a command parser

Nirbhay, Roll No. 230103039 (CS3081). Status: the full implementation is in the repository; the executed and not-executed parts are listed in `report/report.pdf` (Section 9) and `results/current_results.md`.

A 70M-parameter student (EleutherAI/pythia-70m) is trained on the replies of a teacher (phi3.5 on Ollama)
to turn a spoken command into `{"intent", "date", "time", "place"}` JSON, then served from a local
Kubernetes cluster (k3d) with object storage (SeaweedFS). Assignment text: see the course handout;
the unchanged student kit is in `data/`, `tools/` and `network/packets_sample.jsonl`.

```
cluster/k3d.yaml            single-node cluster, host port 8080 -> Traefik
k8s/data                    SeaweedFS (namespace data)           k8s/pipeline  teacher-labelling Job
k8s/app                     Deployment, Service, Ingress, HPA    (namespace app)
prompts/teacher_prompt.txt  teacher prompt                       worker/       worker.py, clean.py, verify_shards.py
training/                   config.yaml, train.py, package.py, evaluate.py, loss.csv
service/                    FastAPI service + Dockerfile         network/      subnets.md, nacl.json
scripts/                    experiment and helper scripts        tests/        unit tests
results/                    evidence: logs, score reports, Locust output
report/report.md            report source (build: make report)   report/report.pdf  submitted report
```

## Requirements on the host
Docker, k3d, kubectl, Python 3.11, curl, openssl, make. The pinned PyTorch/NumPy versions require Python 3.11;
`make setup` defaults to `python3.11` (override with `PYTHON=/path/to/python3.11`). For labelling: Ollama with `ollama pull phi3.5`,
started as `OLLAMA_HOST=0.0.0.0 ollama serve` so that Pods can reach it. For releases: the GitHub CLI (`gh auth login`).
Only free, open-source tools are used; no credentials are stored in the repository (see "Secrets").

On macOS, install missing tools with `brew install python@3.11 k3d kubernetes-cli ollama gh gitleaks pandoc tectonic`
and start Docker Desktop. Report generation uses Pandoc and Tectonic (`make report PDF_ENGINE=pdflatex` also works
if a full LaTeX installation is available). The memory test uses the k3d Docker network and SeaweedFS NodePort 30333;
it does not require enabling Docker Desktop host networking. The cluster's host port remains 8080.

## Build, deploy, test, tear down (from a fresh clone)
```bash
git clone https://github.com/nirbhay-iota/230103039 && cd 230103039
make up        # cluster + SeaweedFS + buckets + images + models from the GitHub Releases + deployment
make test      # unit tests            (make lint: ruff;  make scan: gitleaks)
make loadtest  # the standard 2-minute Locust test through the Ingress (results/loadtest_*.csv)
make down      # delete the cluster
```
Then: `curl -s -X POST localhost:8080/parse -H 'Content-Type: application/json' -d '{"text": "what is the weather in london"}'`

`make up` fills object storage from files in this repository (`data/commands_pool.jsonl`, `data/teacher/shard-*.jsonl`,
`data/v1/train.*`) and from the Releases `model-v1` and `model-v2`; model weights are never committed to Git.

## How each task was produced (and can be reproduced)
| Task | Commands |
|------|----------|
| 1 labelling | `make cluster seed-storage` (or `make up`), `make label` (2 parallel workers, hours on CPU), `make task1-evidence`, `make verify-shards`, `make clean-data`, `make fetch-shards fetch-train` |
| 2 training | `make train` (v1), `make train RUN=v2`, `make train SUBSET=50` (smoke test), `make upload-model RUN=v1`, `make release RUN=v1`, same for v2 |
| 2 evaluation | `make eval-teacher eval-baseline eval-student` (writes `results/*_validation*.json`) |
| 3 service | `make image-app`, `scripts/memtest.sh v1` (50 requests at 1 CPU / 1 GiB), `scripts/exp_fault.sh` |
| 4 Kubernetes | `scripts/exp_notready.sh`, `exp_hpa.sh`, `exp_rolling_update.sh`, `exp_recovery.sh`, `exp_coldstart.sh`, `exp_loadbalance.sh` |
| 5 network | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` |
| 7 cost/SLO | `python scripts/cost_slo.py --stats results/loadtest_stats.csv` |

Experiment scripts must be run from the repository root (Locust reads `data/validation.jsonl`).

## Configuration of the service
`MODEL_URI` (e.g. `s3://models/v1/`), `MODEL_VERSION`, `S3_ENDPOINT`, `MAX_NEW_TOKENS`, and `FAULT_INJECT` (`1` replaces the
model output with `not json`, to show the validation). Credentials come only from the Kubernetes Secret `s3-credentials`.

## Secrets
`scripts/gen-secrets.sh` generates random S3 credentials at deploy time and stores them in Kubernetes Secrets;
nothing is written to the repository. `.gitignore` excludes `.secrets/`, key files and model weights, and CI runs gitleaks.

## Continuous integration
`.github/workflows/ci.yml`: lint, unit tests, model evaluation (downloads the model from the Release, runs `score.py`),
quality gate (`--min-validity 95`), and a gitleaks scan. Run it manually with `model_source = baseline` to see the gate fail.

## Data licence
Commands come from SLURP (Bastianelli et al., EMNLP 2020), CC BY 4.0. Pythia-70M is Apache 2.0; Phi-3.5-mini is MIT.
