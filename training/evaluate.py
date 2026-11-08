"""Run a causal LM (the trained student or the untrained base model) over a labelled file.

    python training/evaluate.py --model artifacts/v1 --input data/validation.jsonl --output results/student_v1_predictions.jsonl
    python training/evaluate.py --model EleutherAI/pythia-70m ...     # the untrained baseline

Writes {"id": ..., "prediction": "<raw model output>"} per line, ready for tools/score.py.
The prompt and the decoding settings are exactly the ones the service uses.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local model directory or Hugging Face model id")
    ap.add_argument("--input", default="data/validation.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-new-tokens", type=int, default=96)
    a = ap.parse_args()

    from runner import ModelRunner

    runner = ModelRunner(a.model, a.max_new_tokens)
    rows = [json.loads(x) for x in open(a.input, encoding="utf-8") if x.strip()]
    out_path = pathlib.Path(a.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with open(out_path, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows, 1):
            f.write(json.dumps({"id": row["id"], "prediction": runner.generate(row["text"])}, ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"{i}/{len(rows)} ({time.time() - started:.0f}s)", flush=True)
    print(f"wrote {len(rows)} predictions to {out_path}")


if __name__ == "__main__":
    main()
