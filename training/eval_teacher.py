"""Score the teacher itself on the validation set (same prompt and settings as Task 1).

    python training/eval_teacher.py --output results/teacher_validation_predictions.jsonl

Needs Ollama running locally with phi3.5 pulled. Uses the worker's own prompt and request code,
so the teacher is queried exactly as it was during labelling (temperature 0, seed 42).
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))
from worker import ask_teacher, build_prompt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/validation.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--model", default="phi3.5")
    ap.add_argument("--prompt", default=str(ROOT / "prompts" / "teacher_prompt.txt"))
    a = ap.parse_args()

    template = open(a.prompt, encoding="utf-8").read()
    rows = [json.loads(x) for x in open(a.input, encoding="utf-8") if x.strip()]
    out = pathlib.Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows, 1):
            reply = ask_teacher(a.ollama_url, a.model, build_prompt(template, row["text"]))
            f.write(json.dumps({"id": row["id"], "prediction": reply}, ensure_ascii=False) + "\n")
            print(f"{i}/{len(rows)}", flush=True)
    print(f"wrote {len(rows)} teacher predictions to {out}")


if __name__ == "__main__":
    main()
