# Evidence

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
