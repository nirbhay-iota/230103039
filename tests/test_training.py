"""Unit tests for Task 2 helpers that do not need PyTorch."""
import hashlib
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "training"))
sys.path.insert(0, str(ROOT / "service"))
import package  # noqa: E402
import train  # noqa: E402
from prompt import build_prompt, build_target  # noqa: E402


class FakeTok:
    eos_token_id = 0

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(c) % 250 + 1 for c in text]}  # one id per character, never 0


def test_config_records_the_required_items():
    cfg = yaml.safe_load((ROOT / "training" / "config.yaml").read_text())
    for key in ("learning_rate", "batch_size", "max_seq_len", "runs", "library_versions"):
        assert key in cfg
    for run in ("v1", "v2"):
        assert "seed" in cfg["runs"][run] and "epochs" in cfg["runs"][run]
    assert cfg["runs"]["v1"]["seed"] != cfg["runs"]["v2"]["seed"] or cfg["runs"]["v1"]["epochs"] != cfg["runs"]["v2"]["epochs"]
    assert cfg["max_train_examples"] == 1500
    assert {"torch", "transformers"} <= set(cfg["library_versions"])


def test_example_has_prompt_masked_and_eos_at_end():
    rec = {"text": "what time is it", "teacher_raw": '{"intent": "datetime_query"}\n'}
    ids, labels, cut = train.encode_example(FakeTok(), rec, 256, loss_on_prompt=False)
    n_prompt = len(build_prompt(rec["text"]))
    assert not cut
    assert labels[:n_prompt] == [-100] * n_prompt
    assert ids[-1] == 0 and labels[-1] == 0
    assert len(ids) == n_prompt + len(build_target(rec["teacher_raw"])) + 1
    assert ids[n_prompt:-1] == [ord(c) % 250 + 1 for c in ' {"intent": "datetime_query"}']  # target is stripped


def test_long_example_is_truncated_and_flagged():
    rec = {"text": "x" * 50, "teacher_raw": "y" * 200}
    ids, labels, cut = train.encode_example(FakeTok(), rec, 64, loss_on_prompt=False)
    assert cut and len(ids) == len(labels) == 64


def test_load_records_takes_only_the_first_n(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("".join(f'{{"id": "C{i}", "text": "t", "teacher_raw": "{{}}"}}\n' for i in range(10)))
    got = train.load_records(p, 4)
    assert [r["id"] for r in got] == ["C0", "C1", "C2", "C3"]


def test_loss_csv_has_one_row_per_epoch_and_replaces_old_run(tmp_path):
    path = tmp_path / "loss.csv"
    train.update_loss_csv(path, "v1", [3.0, 2.0, 1.0])
    train.update_loss_csv(path, "v2", [2.5, 1.5])
    train.update_loss_csv(path, "v1", [3.1, 2.1])  # re-run of v1 replaces its rows
    lines = path.read_text().splitlines()
    assert lines[0] == "run,epoch,train_loss"
    assert [l.split(",")[:2] for l in lines[1:]] == [["v1", "1"], ["v1", "2"], ["v2", "1"], ["v2", "2"]]


def test_package_is_deterministic_and_checksum_file_matches(tmp_path):
    model = tmp_path / "v1"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"weights" * 1000)
    (model / "config.json").write_text("{}")
    (model / "model.sha256").write_text("stale")  # must be excluded from the archive
    archive = tmp_path / "model-v1.tar.gz"
    package.build_archive(model, archive)
    first = package.sha256_of(archive)
    package.build_archive(model, archive)
    assert package.sha256_of(archive) == first
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == first
    import tarfile
    with tarfile.open(archive) as t:
        assert sorted(t.getnames()) == ["config.json", "model.safetensors"]
