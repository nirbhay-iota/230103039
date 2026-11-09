# Use of AI Tools

## Tools
- Claude (Anthropic), used through Claude Code and claude.ai as a coding and documentation assistant.
- phi3.5 served by Ollama, as the teacher model required by the assignment. Its replies are stored exactly as generated.

No other model and no paid inference API was used.

## What the AI was used for
- Reading the assignment and the kit and planning the repository layout.
- Drafting code and configuration: the sharded labelling worker, the cleaning and shard-verification scripts, the training, packaging and evaluation scripts, the FastAPI service and Dockerfile, the Kubernetes manifests, the Makefile, the experiment scripts, the cost and SLO calculator, the CI workflow and the unit tests.
- Working out the subnet allocation and the NACL rules, and drafting `network/subnets.md`.
- Drafting the report and README, and splitting the work into logical commits.

## What the AI did not do
- It did not write or edit any teacher reply. No label was created by hand or by another model.
- No training or evaluation used the validation set. `data/validation.jsonl` is for scoring only, and none of the ten examples in `prompts/teacher_prompt.txt` comes from it (checked by script).
- It did not produce any number in `results/`. Those come from commands run on my machine; the report states which experiments were not run.

## How the output was checked
- Unit tests (`make test`) cover sharding, each cleaning rule, the count identity, checksum reproducibility, packaging determinism, output validation, the NACL rules and the cost formula. 36 passed in my saved run.
- `tools/nacl_sim.py` gives 6 of 6 on the sample packets; additional packets covering the blocked range, SSH sources and reply ports were also tried.
- The subnet table was recomputed with Python's `ipaddress` module.
- Ruff and gitleaks were run locally and passed (`results/setup/`).
- The teacher prompt examples were compared against `validation.jsonl` for overlap.
- Problems found when running the generated code on my machine, such as macOS setup and the container memory check, were fixed in later commits (`fix: support macOS setup and portable container memory checks`).

## Limits
Parts of the AI-written code were not executed before submission: the service image did not build because of a network error while downloading PyTorch, so the service, Kubernetes experiments, training and CI runs are untested end to end. Statements in the report about those parts are labelled as future scope.
