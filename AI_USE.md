# Use of AI tools

## Tools
- **Claude (Anthropic), used through Claude Code / claude.ai**, as a coding assistant for this project.
  The *teacher* labels
  are produced by phi3.5 through Ollama (required by the assignment) and were not written or edited by hand or by Claude.
- **OpenAI Codex**, used for local tool installation, macOS portability fixes, running local checks,
  starting the teacher-labelling pipeline, inspecting failures, and calculating and documenting results from saved outputs.
  Codex preserved teacher replies exactly and did not fabricate missing experiment measurements.

## What the AI was used for
- Reading the handout and the kit, and turning the seven tasks into a repository layout and a work plan.
- Drafting code and configuration: the sharded labelling worker, `clean.py`, `verify_shards.py`, the training and
  packaging scripts, the FastAPI service and Dockerfile, the Kubernetes manifests, the Makefile, the experiment scripts,
  the cost/SLO calculator, the CI workflow, and the unit tests.
- Working out the subnet plan and the NACL rule set, and drafting the explanations in `network/subnets.md`.
- Drafting the structure of the report and this file.
- Splitting the work into logical commits.

## What the AI did not do
- It did not write or edit any teacher reply, and no label was created by hand or by another model.
- It did not train on the validation set. `data/validation.jsonl` is used only for scoring; none of the ten
  examples in `prompts/teacher_prompt.txt` comes from it (checked by script).
- Measured numbers in `results/` and in the report come from running the commands on my own machine, not from the AI.

## How the AI's output was checked
Checks performed while the code was written (in the AI's sandbox, which has no cluster, Ollama or PyTorch):
- Unit tests (`make test`) cover sharding, every cleaning rule, the count identity
  `input = a + b + c + d + duplicates + kept`, checksum reproducibility, packaging determinism, output validation,
  the NACL rules and the cost formula.
- `tools/nacl_sim.py` gives 6/6 on the sample packets; I also tried nine more packets of my own, including the
  198.51.100.0/24 range on web ports and SSH from inside and outside the management subnet.
- The subnet table was recomputed with Python's `ipaddress` module and compared with the hand working.
- The teacher prompt's examples were compared against `validation.jsonl` for overlap.

During the Codex session, the saved local check output recorded 36 passing tests and a passing Ruff check;
the saved gitleaks run found no leaks. Offline cleaning of 250 saved replies retained 112 records.
Full model evaluation and deployment experiments remain unverified. See `results/current_results.md`.

Checks that only I could do, on my machine (fill in what you actually did before you submit):
- [ ] Read the AI-generated code line by line and ran `make train SUBSET=50` to completion.
- [ ] Ran the experiments in `scripts/` against the real cluster and kept their raw output in `results/`.
- [ ] Compared the report's numbers with the files in `results/`.
- [ ] Looked at a sample of raw teacher replies and at the student's errors on the validation set.
- [ ] Anything that failed or had to be corrected after the AI's first version (describe it here):

## Known limits of the AI's help
The initial assistant could not run Kubernetes, Ollama or training. The later Codex session ran setup,
local checks, and part of the Kubernetes/Ollama labelling pipeline, but the image build failed on dependency downloads
and training and deployment experiments did not run. The user then requested that model work stop and that only existing
results be consolidated. Treat anything not backed by a file in `results/` as unverified; the saved shards and counts are partial.
