"""Command-parser inference service (Task 3).

  POST /parse   {"text": "..."} -> 200 with the four-key JSON object (headers X-Model-Version, X-Served-By)
                                    or 500 {"error": "invalid_model_output"}
  GET  /healthz 200 while the process is alive
  GET  /readyz  503 until the model is loaded, then 200

Configuration (environment variables only)
  MODEL_URI        where the model lives in object storage, e.g. s3://models/v1/
  MODEL_VERSION    reported in the X-Model-Version header
  S3_ENDPOINT      object storage URL; credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
                   (a Kubernetes Secret in the cluster)
  MAX_NEW_TOKENS   generation limit
  FAULT_INJECT     when "1", the model output is replaced by "not json" before validation (for testing)
"""
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from validation import download_model, validate_output

log = logging.getLogger("service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class State:
    """Holds the loaded model. `runner` is None until loading has finished."""

    def __init__(self):
        self.runner = None
        self.error = None
        self.lock = threading.Lock()  # one generation at a time per replica


state = State()


def load_model_blocking():
    started = time.time()
    try:
        from runner import ModelRunner

        dest = tempfile.mkdtemp(prefix="model-")
        log.info("downloading model from %s via %s", os.environ["MODEL_URI"], os.environ["S3_ENDPOINT"])
        n = download_model(os.environ["MODEL_URI"], os.environ["S3_ENDPOINT"], dest)
        state.runner = ModelRunner(dest, int(os.environ.get("MAX_NEW_TOKENS", "96")))
        log.info("model %s ready: %d files, %.1fs since start", os.environ.get("MODEL_VERSION"), n, time.time() - started)
    except Exception as exc:  # keep the process alive so /healthz stays 200 and the Pod is simply not Ready
        state.error = repr(exc)
        log.exception("model loading failed")


@asynccontextmanager
async def lifespan(app):
    # Load in the background so that /healthz answers while /readyz still says 503.
    threading.Thread(target=load_model_blocking, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan, title="command-parser")


class ParseRequest(BaseModel):
    text: str


def pod_name():
    return os.environ.get("HOSTNAME", "unknown")  # Kubernetes sets HOSTNAME to the Pod name


@app.get("/healthz")
def healthz():
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    if state.runner is None:
        return JSONResponse({"status": "loading", "error": state.error}, status_code=503)
    return {"status": "ready"}


@app.post("/parse")
def parse(req: ParseRequest):
    if state.runner is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    headers = {"X-Model-Version": os.environ.get("MODEL_VERSION", "unknown"), "X-Served-By": pod_name()}
    with state.lock:
        raw = state.runner.generate(req.text)
    if os.environ.get("FAULT_INJECT") == "1":
        raw = "not json"
    obj = validate_output(raw)
    if obj is None:
        log.warning("invalid model output rejected: %r", raw[:200])
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers)
    return Response(content=json.dumps(obj), media_type="application/json", headers=headers)
