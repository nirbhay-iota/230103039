"""Unit tests for Task 3: output validation and the model download filter."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))
import validation  # noqa: E402

GOOD = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'


def test_service_schema_is_the_assignment_schema():
    assert (ROOT / "service" / "schema.json").read_text() == (ROOT / "data" / "schema.json").read_text()


def test_valid_output_is_accepted_and_keys_are_ordered():
    shuffled = '{"place": null, "time": "seven am", "date": "tomorrow", "intent": "alarm_set"}'
    assert list(validation.validate_output(shuffled)) == ["intent", "date", "time", "place"]
    assert validation.validate_output(GOOD)["time"] == "seven am"


@pytest.mark.parametrize("raw", [
    "not json",
    '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am"',
    '{"intent": "alarm_set", "date": null, "time": null}',
    '{"intent": "alarm_set", "date": null, "time": null, "place": null, "x": 1}',
    '{"intent": "play_music", "date": null, "time": null, "place": null}',
    '{"intent": "alarm_set", "date": 5, "time": null, "place": null}',
    "[1, 2, 3]",
    "",
])
def test_invalid_output_is_rejected(raw):
    assert validation.validate_output(raw) is None


def test_download_skips_checksum_and_nested_keys(monkeypatch, tmp_path):
    import types

    class FakeS3:
        def get_paginator(self, _):
            return types.SimpleNamespace(paginate=lambda **kw: [{"Contents": [
                {"Key": "v1/model.safetensors", "Size": 3}, {"Key": "v1/config.json", "Size": 2},
                {"Key": "v1/model.sha256", "Size": 1}, {"Key": "v1/sub/x", "Size": 1},
                {"Key": "v1/", "Size": 0}]}])

        def download_file(self, bucket, key, dest):
            assert bucket == "models"
            pathlib.Path(dest).write_text(key)

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *a, **k: FakeS3()
    fake_botocore = types.ModuleType("botocore")
    fake_config = types.ModuleType("botocore.config")
    fake_config.Config = lambda **k: None
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config)
    n = validation.download_model("s3://models/v1/", "http://x", str(tmp_path))
    assert n == 2 and sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "model.safetensors"]
