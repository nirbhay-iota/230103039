---
title: "Knowledge Distillation and Deployment of a Command-Parsing Model on a Local Cloud"
author: "NAME, roll number ROLL_NUMBER -- https://github.com/nirbhay-iota/230103039"
geometry: margin=2cm
fontsize: 10pt
---

> **Draft status.** Text marked `[[MEASURE: ...]]` must be replaced with a number from `results/` after you run the experiment.
> Run `python scripts/check_report.py` to list what is still open. Keep *measured* results and *assumptions* in separate
> sentences (the sections below already label them).

**Results snapshot, 9 November 2026.** Existing evidence records 36 passing unit tests, a passing Ruff check,
a clean earlier secret scan, and 6/6 NACL sample decisions. Only 250 teacher replies were saved locally;
their partial cleaning results are below. Model runs have been stopped at the user's request. No training,
validation, service-performance, or load-test measurements are available. See `results/current_results.md`
for the evidence inventory and configuration-based cost calculations. This remains an incomplete report.

# 1. Architecture and decisions

A single-node k3d cluster (`cluster/k3d.yaml`) runs three namespaces. **data**: SeaweedFS with buckets `datasets` and `models`.
**pipeline**: an Indexed Job with two parallel teacher-labelling workers. **app**: the inference Deployment, Service, Ingress and HPA.
The teacher (phi3.5 on Ollama, temperature 0, seed 42) runs on the laptop, outside the cluster, because a 3.8B model is easier to
give CPU and RAM there; Pods reach it as `host.k3d.internal`. The student is trained outside the cluster too (`make train`) and its
files are placed in the `models` bucket and in a GitHub Release; the service image contains no weights and downloads the model at start-up.

Decisions. (1) Credentials are generated per cluster into Kubernetes Secrets, so nothing secret is in Git. (2) `make up` rebuilds the
system from files in the repository plus the model Releases. (3) Rolling updates use `maxUnavailable: 0, maxSurge: 1`, so a Ready Pod
is removed only after its replacement is Ready. (4) The service loads its model in a background thread so `/healthz` answers (liveness)
while `/readyz` returns 503 and the Pod receives no traffic.

# 2. Task 1: object storage and parallel labelling

*Setup.* [[MEASURE: k3d version, SeaweedFS image 3.80, Ollama version, laptop CPU/RAM]]. Buckets `datasets` and `models` exist;
`commands_pool.jsonl` is in `datasets`; the prompt is `prompts/teacher_prompt.txt`.

*Sharding.* Each worker reads `SHARD_INDEX` and `SHARD_COUNT`, takes the commands whose 0-based line number `n` satisfies
`n % SHARD_COUNT == SHARD_INDEX`, and writes its own object `datasets/teacher/shard-<i>.jsonl`. This is a static partition: the
shards are disjoint by construction and together cover every line, so there are no gaps and no repeats without any coordination
between workers (`worker/verify_shards.py` checks it). Round-robin by line number, instead of contiguous blocks, spreads any
difference in command length or order evenly over the workers. The two workers run concurrently as an Indexed Job, which gives each
Pod a completion index that is passed in as `SHARD_INDEX`. A worker flushes its object every 25 records and skips finished ids on
restart, so a crashed Pod loses little work. Assumption: the host runs one Ollama server, so two workers share its CPU and the speed-up
is smaller than 2x; this is a property of one laptop, not of the method.

*Partial local counts* (`results/partial/summary.json`): the saved snapshot contains 125 replies per shard,
250 of 3,000 commands (8.33%). These are not counts for the complete labelling run. The identity
input = (a)+(b)+(c)+(d)+duplicates+kept holds: 250 = 126 + 0 + 1 + 11 + 0 + 112.

| Input records | (a) not valid JSON | (b) wrong keys | (c) bad intent | (d) slot not in command | Duplicates | Kept |
|---|---|---|---|---|---|---|
| 250 (partial) | 126 | 0 | 1 | 11 | 0 | 112 |

Each record is counted under the first rule it fails; duplicates are removed after validity filtering, keeping the smallest id.
The partial cleaned output (`results/partial/train.jsonl`) has SHA-256
`74c6e325f01a379e3ad33b206549f94c12e72166819dc7b0255711c34b7aef0f`.
There are 124 JSON-parseable replies (49.6%) and 112 retained records (44.8%); these are partial-data
cleaning statistics, not validation-set accuracy. Re-running `scripts/summarize_existing_results.py`
reproduces the partial output. The local snapshot lacks 2,750 pool IDs. The full dataset checksum is
[[MEASURE: sha256 of datasets/v1/train.jsonl after the full run is fetched and cleaned]].

# 3. Task 2: training the student

*Setup.* Pythia-70M, full fine-tuning on CPU with PyTorch/Transformers, first 1,500 cleaned records, input
`Command: <text>\nJSON: <teacher reply><eos>`, loss only on the reply. `training/config.yaml`: seed 42, learning rate 3e-4, batch 16,
max length 128, 5 epochs (v1); v2 uses seed 43 and 6 epochs. Training time [[MEASURE]]. Loss per epoch: `training/loss.csv`
(v1 final [[MEASURE]], v2 final [[MEASURE]]). The archive checksum in `models/v1/model.sha256` equals the Release asset's
([[MEASURE: sha256]]).

*Validation results* (100 labelled commands; `results/*_validation.json`):

| Model | json_validity | intent | date | time | place | full_frame |
|---|---|---|---|---|---|---|
| Teacher phi3.5 | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] |
| Pythia-70M, untrained | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] |
| Student v1 | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] |
| Student v2 | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] | [[MEASURE]] |

*What changed.* [[MEASURE: discuss: validity before/after, which slots are hardest, student vs teacher, v1 vs v2, examples of errors from the raw outputs]].
*Suitability of Pythia-70M.* [[MEASURE: your assessment, based on the table: size, English-only pre-training, 2,048-token context, ability to hold the JSON format]].

*Sequence-level vs logit-based distillation.* In **sequence-level** distillation (Kim and Rush, 2016) the teacher decodes an output
for every input and the student is trained with ordinary cross-entropy on that decoded text, as if it were a label; the teacher's
text is the only thing the student sees. In **logit-based** distillation the student is trained to match the teacher's full
probability distribution over the vocabulary at every output position, typically by minimising a KL divergence between the two
softmax outputs, so it also learns which alternatives the teacher considered likely. It is not possible here because (i) the teacher
(Phi-3.5, its own tokenizer) and the student (Pythia, the GPT-NeoX tokenizer) have different vocabularies, so their per-token
distributions cannot be compared position by position, and (ii) Ollama's generation API returns the generated text, not the full
vocabulary distribution at each step, so the teacher's logits are not available to store. One limitation of what I did: the student can
only copy what the teacher wrote, including its mistakes and its departures from the dataset's labelling conventions, and it sees a
single greedy sample per command rather than the teacher's uncertainty, so the teacher's score is a practical ceiling for it.

# 4. Task 3: the inference service

FastAPI service (`service/`), port 8000: `POST /parse` (headers `X-Model-Version`, `X-Served-By`), `GET /healthz`, `GET /readyz`.
Output is validated against `schema.json` with `jsonschema`; anything invalid becomes HTTP 500 `{"error": "invalid_model_output"}`
([[MEASURE: results/task3/fault_inject.txt]]). Configuration: `MODEL_URI`, `MODEL_VERSION`, `S3_ENDPOINT`, `MAX_NEW_TOKENS`, and
`FAULT_INJECT`; credentials only from the Secret. Image: pinned dependencies, CPU-only PyTorch, no weights; size [[MEASURE: docker image ls]]
(limit 2 GB). *Memory test:* 50 sequential requests at `--cpus=1 --memory=1g`: [[MEASURE: ok/50, OOMKilled, peak memory from results/task3/memtest.txt]].

# 5. Task 4: Kubernetes deployment, scaling and reliability

All numbers below come from `results/task4/`. Resources: requests 500m / 512Mi, limits 1 CPU / 1 GiB. Probes: liveness `/healthz`, readiness `/readyz`.

| Experiment | Result |
|---|---|
| Service has no ready endpoints while the model loads | [[MEASURE: notready_endpoints.log]] |
| HPA 1 to 2 under load and back to 1 | [[MEASURE: hpa_watch.log: times and CPU %]] |
| Rolling update v1 to v2 under load | [[MEASURE: failed requests / total = x %]]; rollback shows `X-Model-Version: v1` [[MEASURE]] |
| Pod deleted under load | replicas restored in [[MEASURE]] s; failed requests [[MEASURE]] % |
| Cold start (three runs) | [[MEASURE: t1, t2, t3]] s, median [[MEASURE]] s; log lines show the download from `s3://models/v1/` |
| Load balancing, 2 replicas, standard test | [[MEASURE: requests served by each replica and %]] |

*Limitation of the local cluster.* The cluster is one node on one laptop. Deleting Pods shows that Kubernetes re-creates them, but it does
not demonstrate tolerance to the loss of a machine, network partitions, or zone failures: if the laptop or Docker stops, everything stops.
Autoscaling from 1 to 2 replicas also competes for the same CPU cores that the load generator uses, so the scaling behaviour seen here is
only indicative. [[MEASURE: note anything else you observed, e.g. HPA delay]].

# 6. Task 5: subnetting and NACL

Allocation of `10.20.0.0/16` from the largest need to the smallest (working in `network/subnets.md`):

| Subnet | Network | Prefix | Usable range | Broadcast | Usable hosts |
|---|---|---|---|---|---|
| app | 10.20.0.0 | /22 | 10.20.0.1 - 10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 10.20.4.0 | /24 | 10.20.4.1 - 10.20.4.254 | 10.20.4.255 | 254 |
| data | 10.20.5.0 | /25 | 10.20.5.1 - 10.20.5.126 | 10.20.5.127 | 126 |
| management | 10.20.5.128 | /27 | 10.20.5.129 - 10.20.5.158 | 10.20.5.159 | 30 |

`network/nacl.json` (public subnet). Inbound: 100 deny all from 198.51.100.0/24; 110 allow tcp 80 and 120 allow tcp 443 from anywhere;
130 allow tcp 22 from 10.20.5.128/27; 140 allow tcp 1024-65535 from 10.20.0.0/22 (replies from the app subnet). Outbound: 100 allow tcp 8000
to 10.20.0.0/22; 110 allow tcp 1024-65535 to anywhere (replies to clients). `nacl_sim.py --check` gives 6/6 (`results/nacl_check.txt`).

A NACL is stateless: it keeps no record of connections, so a reply is just another packet and needs its own rule. That is why replies to
clients (outbound 110) and replies from the app subnet (inbound 140) are allowed explicitly, on the ephemeral ports. Rules are checked from the
lowest number up and the first match wins, so the deny for 198.51.100.0/24 must have a lower number (100) than the allows for ports 80 and 443
(110, 120); otherwise a packet from that range to port 443 would match the allow first and the block would never apply.

# 7. Task 6: reproducibility, testing and CI/CD

`make up` builds and deploys from a fresh clone in one command, `make down` deletes the cluster. The workflow `.github/workflows/ci.yml` has the stages
lint, unit tests (36 passed locally in 1.48 seconds; `results/setup/tests_and_lint.txt`), model evaluation from the Release asset, and the quality gate `score.py --min-validity 95`; a gitleaks job scans the history.
Failed run with the untrained Pythia-70M (gate working): [[MEASURE: link to the failed GitHub Actions run]]. Passing run with the trained model: [[MEASURE: link]].
The saved local secret scan found no leaks across 13 commits (approximately 364,783 bytes);
it predates the results-documentation changes and does not establish CI status. AI use is described in `AI_USE.md`.

# 8. Task 7: performance, cost and review

Standard load test (4 users, 2 minutes, through the Ingress, 2 replicas; `results/loadtest_stats.csv`): p50 [[MEASURE]] ms, p95 [[MEASURE]] ms,
throughput [[MEASURE]] req/s, error rate [[MEASURE]] %, cold start (median of three) [[MEASURE]] s. `kubectl top pods` during the test: [[MEASURE: CPU and memory of each Pod]].

*Cost* (`scripts/cost_slo.py`, hypothetical rate card; assumption: billing by limits for every hour a replica runs): hourly cost = 2 x (1 vCPU x 3.50 + 1 GiB x 0.45) = 7.90;
requests per hour = [[MEASURE]] x 3600 = [[MEASURE]]; cost per 1,000 requests = 7.90 / [[MEASURE]] x 1000 = [[MEASURE]] INR.

The calculable configuration-based costs are INR 3.50 CPU + INR 0.45 memory = INR 3.95 per replica-hour,
or INR 7.90 for two replicas. If measured throughput is `r` requests/s, cost per 1,000 requests is
`2.194444 / r` INR. A numeric value needs the missing load-test results; no throughput is assumed.

*SLO.* "99% of requests succeed (HTTP 200 within 30 s)", window: one load-test run. Error budget = 1% of [[MEASURE: total requests]] = [[MEASURE]] requests;
failed requests [[MEASURE]], so [[MEASURE]]% of the budget was used.

*Review* (every Evidence cell needs a measured value):

| Component or concern | Evidence (measured number) | Limitation found | Improvement proposed |
|---|---|---|---|
| Data and storage | [[MEASURE: e.g. records kept, shard sizes]] | [[MEASURE]] | [[MEASURE]] |
| Model quality | [[MEASURE: validation full_frame]] | [[MEASURE]] | [[MEASURE]] |
| Latency and throughput | [[MEASURE: p95, req/s]] | [[MEASURE]] | [[MEASURE]] |
| Resource utilisation | [[MEASURE: kubectl top, peak memory]] | [[MEASURE]] | [[MEASURE]] |
| Reliability and recovery | [[MEASURE: failed % in rollout/recovery]] | [[MEASURE]] | [[MEASURE]] |
| Security and cost | [[MEASURE: gitleaks result, cost per 1,000]] | [[MEASURE]] | [[MEASURE]] |

# References

Kim and Rush, *Sequence-Level Knowledge Distillation*, EMNLP 2016. Bastianelli et al., *SLURP*, EMNLP 2020 (CC BY 4.0). EleutherAI Pythia-70M model card (Apache 2.0).
Phi-3.5-mini-instruct on Ollama. k3d, SeaweedFS, Kubernetes, Locust and gitleaks documentation.
