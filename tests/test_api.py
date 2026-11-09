"""HTTP API tests for the inference service (Task 3). They need fastapi and httpx and run in CI;
they are skipped on machines where those packages are not installed."""
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "service"))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

GOOD = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'


class FakeRunner:
    def __init__(self, text):
        self.text = text

    def generate(self, _):
        return self.text


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("MODEL_VERSION", "vtest")
    monkeypatch.setenv("HOSTNAME", "pod-abc")
    monkeypatch.delenv("FAULT_INJECT", raising=False)
    import app as appmod
    monkeypatch.setattr(appmod, "load_model_blocking", lambda: None)
    appmod.state.runner = None
    with TestClient(appmod.app) as client:
        yield client, appmod
    appmod.state.runner = None


def test_health_always_ok_and_ready_is_503_until_loaded(api):
    client, appmod = api
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    assert client.post("/parse", json={"text": "hi"}).status_code == 503
    appmod.state.runner = FakeRunner(GOOD)
    assert client.get("/readyz").status_code == 200


def test_parse_returns_exact_body_and_both_headers(api):
    client, appmod = api
    appmod.state.runner = FakeRunner(GOOD)
    r = client.post("/parse", json={"text": "set an alarm for seven am tomorrow"})
    assert r.status_code == 200
    assert r.json() == json.loads(GOOD) and list(r.json()) == ["intent", "date", "time", "place"]
    assert r.headers["X-Model-Version"] == "vtest" and r.headers["X-Served-By"] == "pod-abc"


def test_broken_model_output_gives_500_never_200(api):
    client, appmod = api
    appmod.state.runner = FakeRunner('{"intent": "alarm_set", "date": "tom')
    r = client.post("/parse", json={"text": "x"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_fault_injection_replaces_output(api, monkeypatch):
    client, appmod = api
    appmod.state.runner = FakeRunner(GOOD)
    monkeypatch.setenv("FAULT_INJECT", "1")
    r = client.post("/parse", json={"text": "x"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}
    monkeypatch.setenv("FAULT_INJECT", "0")
    assert client.post("/parse", json={"text": "x"}).status_code == 200
