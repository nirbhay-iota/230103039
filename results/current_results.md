# Results available on 9 November 2026

These results use saved files only. No model inference, training, new test run, or load test was performed to prepare this summary.

## Task 1: partial local teacher data

The two locally saved shards contain **125 replies each**, or **250 / 3,000 commands (8.33%)**.
They are an earlier snapshot of the labelling run, not its final output. A later saved Kubernetes status
(`task1/job_status_before_stop.json`) reports completion index 0 succeeded and one worker active;
it does not contain that worker's replies. Docker was stopped when results were consolidated, so newer
objects were not fetched. The Ollama model and server were stopped; suspending the Job could not be
confirmed because the Kubernetes API was unavailable. Keep Docker stopped until model work is wanted again.

Offline cleaning of the saved replies gives:

| Input records | (a) Invalid JSON | (b) Wrong keys | (c) Bad intent | (d) Bad slot | Duplicates | Kept |
|---:|---:|---:|---:|---:|---:|---:|
| 250 | 126 | 0 | 1 | 11 | 0 | 112 |

Count check: **250 = 126 + 0 + 1 + 11 + 0 + 112**.

- JSON-parseable raw replies: **124 / 250 = 49.6%**. This is a parsing check on partial training-pool replies, not a validation-set score.
- Retained after all cleaning rules: **112 / 250 = 44.8%**.
- The available shards have no repeated or misplaced IDs, but **2,750 pool IDs are missing from the local snapshot**.
- Some replies append explanatory notes to JSON and are rejected as invalid JSON. Raw replies were preserved without edits.
- Partial cleaned output: `partial/train.jsonl`; SHA-256: `74c6e325f01a379e3ad33b206549f94c12e72166819dc7b0255711c34b7aef0f`.

The partial output is stored separately from `data/v1/`; it is not the completed training dataset.
Counts and source checksums are in `partial/summary.json`. Recalculate offline with
`.venv/bin/python scripts/summarize_existing_results.py`.

## Tasks 3–4: build and cluster evidence

Saved Task 1 logs show SeaweedFS Ready in namespace `data`, and two workers in namespace `pipeline`
with indices 0 and 1 and the same recorded start time, `2026-11-08T21:17:32Z` (9 November, 02:47:32 IST).
The saved bootstrap log records creation of both buckets and upload of the command pool.

The inference image did not finish building: its last attempt failed while downloading a dependency
from `download.pytorch.org` (`Network is unreachable`). See `setup/app_build_failed.log`.
There is no completed image-size, memory, service, HPA, rollout, recovery, cold-start, or load-balancing measurement.

## Task 5: network check

The saved NACL simulator output records **6 / 6 correct decisions (100%)** on the supplied sample packets.
This does not establish performance on the hidden packet set. Subnet capacities are 1,022, 254, 126,
and 30 usable hosts, as calculated in `network/subnets.md`.

## Task 6: saved local checks

- **36 tests passed**, one deprecation warning, **1.48 seconds** in the saved run.
- Ruff: **all checks passed**.
- Gitleaks: **no leaks found**, scanning **13 commits**, approximately **364,783 bytes**.

These refer to the earlier saved check outputs in `setup/`, not a new scan of this documentation commit.
No GitHub Actions pass/fail run is recorded yet.

## Task 7: cost calculations supported by configuration

Using the hypothetical rate card and configured limits of 1 vCPU / 1 GiB per replica:

1. CPU per replica-hour: 1 × 3.50 = **INR 3.50**.
2. Memory per replica-hour: 1 × 0.45 = **INR 0.45**.
3. Total per replica-hour: 3.50 + 0.45 = **INR 3.95**.
4. Two configured replicas: 2 × 3.95 = **INR 7.90/hour**.
5. For measured throughput `r` requests/second, requests/hour = `3,600r` and
   cost/1,000 requests = `7.90 × 1,000 / (3,600r)` = **`2.194444 / r` INR**.

This is a configuration-based estimate, not an observed bill or proof that two replicas ran.
No throughput CSV exists, so a numeric cost per 1,000 requests cannot be reported.
For a 99% success SLO over one load-test run with `N` requests and `F` failures, the error budget is
`0.01N` requests and budget used is `100F / (0.01N)%`. Neither `N` nor `F` has been measured.
Latency, throughput, error rate, pod resources, and cold-start time remain unmeasured.

## Unavailable results

No trained student, epoch-loss CSV, teacher/baseline/student validation report, model Release,
or load-test output exists locally. No model accuracy or deployment-performance numbers are inferred
from unit tests, partial data, or configuration. The report remains a draft and no `final` tag was created.
