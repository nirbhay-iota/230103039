# Evidence

The results currently available are summarized in [current_results.md](current_results.md).
`partial/summary.json` and `partial/train.*` contain calculations from **250 saved replies only**;
they are not the completed dataset or validation results. The table below lists expected outputs,
not a claim that every file exists.

Everything here is produced by running the commands in the top-level README. Expected files:

| File(s) | Produced by |
|---------|-------------|
| `nacl_check.txt` | `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` |
| `task1/` (pods, worker logs, shard indexes) | `make task1-evidence` |
| `clean_counts.json` | `make clean-data` |
| `teacher_validation.json`, `*_predictions.jsonl` | `make eval-teacher` |
| `baseline_validation*.json(l)` | `make eval-baseline` |
| `student_v1_validation*.json(l)`, `student_v2_...` | `make eval-student RUN=v1` / `RUN=v2` |
| `task3/` (memtest, fault injection) | `scripts/memtest.sh`, `scripts/exp_fault.sh` |
| `task4/` (rolling update, recovery, cold start, HPA, not-ready, load balancing) | `scripts/exp_*.sh` |
| `loadtest_stats.csv`, `loadtest_headers.json` | `scripts/exp_loadbalance.sh` / `make loadtest` |
| `cost_slo.md` | `python scripts/cost_slo.py` |
| `partial/summary.json`, `partial/train.*` | `python scripts/summarize_existing_results.py` (offline, existing shards only) |
| `setup/` | Saved setup, test, lint, secret-scan, and failed image-build logs |
