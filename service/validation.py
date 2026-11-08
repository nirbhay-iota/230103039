"""Output validation and model download helpers (no web framework, no PyTorch)."""
import json
import logging
import os
import pathlib
from urllib.parse import urlparse

import jsonschema

log = logging.getLogger("service")

SCHEMA_PATH = pathlib.Path(os.environ.get("SCHEMA_PATH", pathlib.Path(__file__).with_name("schema.json")))
SKIP_FILES = {"model.sha256"}
KEY_ORDER = ("intent", "date", "time", "place")


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["json_schema"]


SCHEMA = load_schema()


def validate_output(raw, schema=SCHEMA):
    """Return the parsed object if `raw` is a valid four-key command, otherwise None."""
    try:
        obj = json.loads(raw)
        jsonschema.validate(obj, schema)
    except (json.JSONDecodeError, jsonschema.ValidationError, TypeError):
        return None
    return {k: obj[k] for k in KEY_ORDER}


def download_model(model_uri, endpoint, dest):
    """Download every object under model_uri (s3://bucket/prefix/) into dest."""
    import boto3
    from botocore.config import Config

    parsed = urlparse(model_uri)
    bucket, prefix = parsed.netloc, parsed.path.lstrip("/")
    prefix = prefix if prefix.endswith("/") else prefix + "/"
    s3 = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1",
                      config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}))
    count = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            name = obj["Key"][len(prefix):]
            if not name or "/" in name or name in SKIP_FILES:
                continue
            s3.download_file(bucket, obj["Key"], str(pathlib.Path(dest) / name))
            count += 1
            log.info("downloaded %s (%d bytes)", obj["Key"], obj["Size"])
    if count == 0:
        raise RuntimeError(f"no model files found under {model_uri}")
    return count
