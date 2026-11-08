"""Teacher-labelling worker (Task 1).

Reads commands_pool.jsonl from object storage, keeps the lines whose 0-based line number
leaves remainder SHARD_INDEX when divided by SHARD_COUNT, sends each command to the teacher
(phi3.5 on Ollama, temperature 0, seed 42) and writes one line per command to its own object:

    {"id": "...", "text": "...", "teacher_raw": "<the teacher's exact reply>"}

Environment variables
    SHARD_INDEX   0-based shard number (required)
    SHARD_COUNT   total number of shards (required)
    S3_ENDPOINT   object storage URL (credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
    OLLAMA_URL    default http://host.k3d.internal:11434
    TEACHER_MODEL default phi3.5
    PROMPT_FILE   default /app/teacher_prompt.txt (the template contains {command})
    INPUT_BUCKET / INPUT_KEY / OUTPUT_BUCKET / OUTPUT_PREFIX  default datasets, commands_pool.jsonl, datasets, teacher
    FLUSH_EVERY   upload the shard object after this many new records (default 25)

The worker is resumable: if its shard object already exists, finished ids are kept and skipped.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

TEMPERATURE = 0
SEED = 42
NUM_PREDICT = 160


def shard_records(lines, shard_index, shard_count):
    """Yield (line_number, record) for lines with line_number % shard_count == shard_index."""
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError(f"bad shard settings: index={shard_index} count={shard_count}")
    for number, line in enumerate(lines):
        if number % shard_count != shard_index or not line.strip():
            continue
        yield number, json.loads(line)


def build_prompt(template, command):
    # str.replace, not str.format: the template contains literal JSON braces.
    return template.replace("{command}", command)


def ask_teacher(ollama_url, model, prompt, retries=5):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": TEMPERATURE, "seed": SEED, "num_predict": NUM_PREDICT},
    }).encode()
    delay = 2
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(f"{ollama_url}/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())["response"]  # stored exactly as generated
        except (urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
            if attempt == retries:
                raise
            print(f"teacher call failed ({exc}); retry {attempt}/{retries - 1} in {delay}s", flush=True)
            time.sleep(delay)
            delay *= 2


def encode_shard(done):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in done)


def main():
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError

    index, count = int(os.environ["SHARD_INDEX"]), int(os.environ["SHARD_COUNT"])
    ollama = os.environ.get("OLLAMA_URL", "http://host.k3d.internal:11434")
    model = os.environ.get("TEACHER_MODEL", "phi3.5")
    in_bucket = os.environ.get("INPUT_BUCKET", "datasets")
    in_key = os.environ.get("INPUT_KEY", "commands_pool.jsonl")
    out_bucket = os.environ.get("OUTPUT_BUCKET", "datasets")
    out_key = f"{os.environ.get('OUTPUT_PREFIX', 'teacher').strip('/')}/shard-{index}.jsonl"
    flush_every = int(os.environ.get("FLUSH_EVERY", "25"))
    template = open(os.environ.get("PROMPT_FILE", "/app/teacher_prompt.txt"), encoding="utf-8").read()

    s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                      config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 5}))
    lines = s3.get_object(Bucket=in_bucket, Key=in_key)["Body"].read().decode("utf-8").splitlines()
    todo = list(shard_records(lines, index, count))

    done = []
    try:
        existing = s3.get_object(Bucket=out_bucket, Key=out_key)["Body"].read().decode("utf-8")
        done = [json.loads(x) for x in existing.splitlines() if x.strip()]
        print(f"resuming shard {index}: {len(done)} records already labelled", flush=True)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("NoSuchKey", "404"):
            raise
    finished = {r["id"] for r in done}

    def flush():
        s3.put_object(Bucket=out_bucket, Key=out_key, Body=encode_shard(done).encode("utf-8"))

    print(f"shard {index}/{count}: {len(todo)} commands, {len(todo) - len(finished)} to label", flush=True)
    new = 0
    for _, rec in todo:
        if rec["id"] in finished:
            continue
        raw = ask_teacher(ollama, model, build_prompt(template, rec["text"]))
        done.append({"id": rec["id"], "text": rec["text"], "teacher_raw": raw})
        new += 1
        if new % flush_every == 0:
            flush()
            print(f"shard {index}: {len(done)}/{len(todo)} done", flush=True)
    flush()
    print(f"shard {index}: finished with {len(done)} records -> s3://{out_bucket}/{out_key}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
