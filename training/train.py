"""Sequence-level knowledge distillation: fine-tune Pythia-70M on the teacher's JSON replies (Task 2).

    python training/train.py --config training/config.yaml --run v1 [--subset 50]

Each example is   "Command: <command>\\nJSON: <teacher JSON reply>"   followed by the end-of-text token.
The loss is computed on the reply only (config: loss_on_prompt). CPU only.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import pathlib
import platform
import random
import sys
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))
from prompt import build_prompt, build_target  # noqa: E402


def set_seed(seed):
    import numpy as np
    import torch
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_records(path, limit):
    """The first `limit` records of the cleaned dataset (it is already in id order)."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
            if len(records) == limit:
                break
    return records


def encode_example(tok, record, max_len, loss_on_prompt):
    prompt_ids = tok(build_prompt(record["text"]), add_special_tokens=False)["input_ids"]
    target_ids = tok(build_target(record["teacher_raw"]), add_special_tokens=False)["input_ids"]
    target_ids = target_ids + [tok.eos_token_id]
    ids = prompt_ids + target_ids
    labels = (prompt_ids if loss_on_prompt else [-100] * len(prompt_ids)) + target_ids
    truncated = len(ids) > max_len
    return ids[:max_len], labels[:max_len], truncated


def make_batches(examples, batch_size, pad_id, generator):
    import torch
    order = torch.randperm(len(examples), generator=generator).tolist()
    for start in range(0, len(order), batch_size):
        chunk = [examples[i] for i in order[start:start + batch_size]]
        width = max(len(ids) for ids, _ in chunk)
        input_ids = torch.full((len(chunk), width), pad_id, dtype=torch.long)
        labels = torch.full((len(chunk), width), -100, dtype=torch.long)
        mask = torch.zeros((len(chunk), width), dtype=torch.long)
        for row, (ids, lab) in enumerate(chunk):
            input_ids[row, :len(ids)] = torch.tensor(ids)
            labels[row, :len(lab)] = torch.tensor(lab)
            mask[row, :len(ids)] = 1
        yield input_ids, mask, labels


def update_loss_csv(path, run, losses):
    """Keep one row per (run, epoch); replace this run's old rows."""
    path = pathlib.Path(path)
    rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["run"] != run]
    rows += [{"run": run, "epoch": e, "train_loss": f"{v:.6f}"} for e, v in enumerate(losses, 1)]
    rows.sort(key=lambda r: (r["run"], int(r["epoch"])))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["run", "epoch", "train_loss"])
        w.writeheader()
        w.writerows(rows)


def check_versions(wanted):
    import numpy
    import torch
    import transformers
    have = {"python": ".".join(platform.python_version_tuple()[:2]), "torch": torch.__version__.split("+")[0],
            "transformers": transformers.__version__, "numpy": numpy.__version__, "PyYAML": yaml.__version__}
    for name, version in have.items():
        if str(wanted.get(name)) != version:
            print(f"WARNING: config.yaml lists {name} {wanted.get(name)} but {version} is installed", flush=True)
    return have


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--run", default="v1")
    ap.add_argument("--subset", type=int, default=0, help="train on only the first N records (smoke test)")
    a = ap.parse_args()

    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    if a.run not in cfg["runs"]:
        sys.exit(f"unknown run {a.run!r}; config.yaml defines {sorted(cfg['runs'])}")
    seed, epochs = cfg["runs"][a.run]["seed"], cfg["runs"][a.run]["epochs"]
    if a.subset:
        epochs = min(epochs, 2)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    installed = check_versions(cfg["library_versions"])
    set_seed(seed)
    torch.set_num_threads(os.cpu_count() or 1)

    limit = a.subset or cfg["max_train_examples"]
    train_path = ROOT / cfg["train_file"]
    records = load_records(train_path, limit)
    if not records:
        sys.exit(f"no training records found in {train_path}")
    print(f"run {a.run}: {len(records)} records, seed {seed}, {epochs} epochs", flush=True)

    tok = AutoTokenizer.from_pretrained(cfg["base_model"])
    tok.pad_token = tok.eos_token
    examples, truncated = [], 0
    for r in records:
        ids, labels, cut = encode_example(tok, r, cfg["max_seq_len"], cfg["loss_on_prompt"])
        examples.append((ids, labels))
        truncated += cut
    print(f"{truncated} examples were longer than max_seq_len={cfg['max_seq_len']} and truncated", flush=True)

    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"])
    model.train()
    bs = cfg["batch_size"]
    steps_per_epoch = math.ceil(len(examples) / bs)
    total_steps = steps_per_epoch * epochs
    warmup = max(1, int(cfg["warmup_ratio"] * total_steps))
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warmup if s < warmup else max(0.0, (total_steps - s) / max(1, total_steps - warmup)))

    generator = torch.Generator().manual_seed(seed)
    epoch_losses, step, started = [], 0, time.time()
    for epoch in range(1, epochs + 1):
        weighted, tokens = 0.0, 0
        for input_ids, mask, labels in make_batches(examples, bs, tok.pad_token_id, generator):
            out = model(input_ids=input_ids, attention_mask=mask, labels=labels)
            n = int((labels[:, 1:] != -100).sum())
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), cfg["max_grad_norm"])
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            weighted += out.loss.item() * n
            tokens += n
            step += 1
            if step % 20 == 0:
                print(f"  step {step}/{total_steps} loss {out.loss.item():.4f}", flush=True)
        epoch_losses.append(weighted / max(tokens, 1))
        print(f"epoch {epoch}/{epochs}: train loss {epoch_losses[-1]:.4f} ({time.time() - started:.0f}s)", flush=True)

    name = a.run + (f"-subset{a.subset}" if a.subset else "")
    out_dir = ROOT / cfg["output_root"] / name
    out_dir.mkdir(parents=True, exist_ok=True)
    model.eval()
    model.save_pretrained(out_dir, safe_serialization=True)
    tok.save_pretrained(out_dir)
    info = {
        "run": a.run, "model_version": name, "base_model": cfg["base_model"], "seed": seed, "epochs": epochs,
        "learning_rate": cfg["learning_rate"], "batch_size": bs, "max_seq_len": cfg["max_seq_len"],
        "train_records": len(records), "epoch_losses": epoch_losses, "libraries": installed,
        "train_file_sha256": hashlib.sha256(train_path.read_bytes()).hexdigest(),
    }
    (out_dir / "version.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    csv_path = ROOT / (cfg["subset_loss_csv"] if a.subset else cfg["loss_csv"])
    update_loss_csv(csv_path, name, epoch_losses)
    print(f"saved model, tokenizer and version.json to {out_dir}; losses written to {csv_path}", flush=True)


if __name__ == "__main__":
    main()
