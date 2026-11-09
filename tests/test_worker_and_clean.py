"""Unit tests for Task 1: sharding, cleaning rules, checksum reproducibility."""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "worker"))
import clean  # noqa: E402
import verify_shards  # noqa: E402
import worker  # noqa: E402

INTENTS = clean.load_intents(ROOT / "data" / "schema.json")


def rec(i, text, raw):
    return {"id": f"C{i:04d}", "text": text, "teacher_raw": raw}


GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


def test_sharding_uses_line_number_remainder():
    lines = [json.dumps({"id": f"C{i}", "text": "t"}) for i in range(10)]
    shard0 = [n for n, _ in worker.shard_records(lines, 0, 3)]
    shard1 = [n for n, _ in worker.shard_records(lines, 1, 3)]
    shard2 = [n for n, _ in worker.shard_records(lines, 2, 3)]
    assert shard0 == [0, 3, 6, 9] and shard1 == [1, 4, 7] and shard2 == [2, 5, 8]
    assert sorted(shard0 + shard1 + shard2) == list(range(10))


def test_real_pool_is_partitioned_exactly():
    lines = (ROOT / "data" / "commands_pool.jsonl").read_text().splitlines()
    ids = []
    for k in range(2):
        ids += [r["id"] for _, r in worker.shard_records(lines, k, 2)]
    assert len(ids) == len(set(ids)) == 3000


def test_prompt_substitution_keeps_json_braces():
    template = (ROOT / "prompts" / "teacher_prompt.txt").read_text()
    prompt = worker.build_prompt(template, "what time is it in rome")
    assert prompt.rstrip().endswith("Command: what time is it in rome")
    assert '{"intent": "alarm_set"' in prompt and "{command}" not in prompt


def test_each_rejection_rule():
    cmd = "what is the weather in london"
    assert clean.classify(rec(1, cmd, GOOD), INTENTS) is None
    assert clean.classify(rec(1, cmd, "not json"), INTENTS) == "a_invalid_json"
    assert clean.classify(rec(1, cmd, '{"intent": "weather_query", "date": nu'), INTENTS) == "a_invalid_json"
    assert clean.classify(rec(1, cmd, '{"intent": "weather_query"}'), INTENTS) == "b_bad_keys"
    extra = '{"intent": "weather_query", "date": null, "time": null, "place": null, "x": 1}'
    assert clean.classify(rec(1, cmd, extra), INTENTS) == "b_bad_keys"
    assert clean.classify(rec(1, cmd, "[1, 2]"), INTENTS) == "b_bad_keys"
    bad_intent = '{"intent": "play_music", "date": null, "time": null, "place": null}'
    assert clean.classify(rec(1, cmd, bad_intent), INTENTS) == "c_bad_intent"
    invented = '{"intent": "weather_query", "date": null, "time": null, "place": "paris"}'
    assert clean.classify(rec(1, cmd, invented), INTENTS) == "d_bad_slot"
    number = '{"intent": "weather_query", "date": null, "time": 5, "place": "london"}'
    assert clean.classify(rec(1, cmd, number), INTENTS) == "d_bad_slot"
    empty = '{"intent": "weather_query", "date": "", "time": null, "place": "london"}'
    assert clean.classify(rec(1, cmd, empty), INTENTS) == "d_bad_slot"


def test_counts_add_up_and_smallest_id_wins_and_sorted():
    records = [
        rec(5, "what is the weather in london", GOOD),
        rec(2, "what is the weather in london", GOOD),
        rec(9, "what is the weather in london", "garbage"),
        rec(1, "what time is it in tokyo", '{"intent": "datetime_query", "date": null, "time": null, "place": "tokyo"}'),
        rec(7, "hello", '{"intent": "nope", "date": null, "time": null, "place": null}'),
    ]
    kept, counts = clean.clean(records, INTENTS)
    assert [r["id"] for r in kept] == ["C0001", "C0002"]
    assert counts == {"input_records": 5, "a_invalid_json": 1, "b_bad_keys": 0, "c_bad_intent": 1,
                      "d_bad_slot": 0, "duplicates": 1, "kept": 2}
    assert counts["input_records"] == sum(v for k, v in counts.items() if k != "input_records")


def test_clean_is_reproducible_and_checksum_matches(tmp_path):
    shards = tmp_path / "shards"
    shards.mkdir()
    rows = [rec(i, f"what is the weather in city{i}", GOOD.replace("london", f"city{i}")) for i in range(1, 21)]
    (shards / "shard-1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows[10:]))
    (shards / "shard-0.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reversed(rows[:10])))
    digests = []
    for run in ("a", "b"):
        out = tmp_path / run
        subprocess.run([sys.executable, str(ROOT / "worker" / "clean.py"), "--local-dir", str(shards),
                        "--out-dir", str(out)], check=True, capture_output=True)
        recorded = (out / "train.sha256").read_text().split()[0]
        assert recorded == hashlib.sha256((out / "train.jsonl").read_bytes()).hexdigest()
        digests.append(recorded)
    assert digests[0] == digests[1]
    ids = [json.loads(x)["id"] for x in (tmp_path / "a" / "train.jsonl").read_text().splitlines()]
    assert ids == sorted(ids) and len(ids) == 20


def test_verify_shards_detects_gap_and_repeat():
    pool = [json.dumps({"id": f"C{i}", "text": "t"}) for i in range(6)]
    ok = {0: [{"id": "C0"}, {"id": "C2"}, {"id": "C4"}], 1: [{"id": "C1"}, {"id": "C3"}, {"id": "C5"}]}
    assert verify_shards.verify(pool, ok, 2) == []
    gap = {0: ok[0][:2], 1: ok[1]}
    assert any("missing" in p for p in verify_shards.verify(pool, gap, 2))
    repeat = {0: ok[0] + [{"id": "C1"}], 1: ok[1]}
    assert any("more than once" in p or "another shard" in p for p in verify_shards.verify(pool, repeat, 2))


def test_ask_teacher_sends_fixed_settings_and_returns_exact_reply():
    import http.server
    import threading

    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.update(body, path=self.path)
            reply = json.dumps({"response": ' {"intent": "x"}\n\n'}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = worker.ask_teacher(f"http://127.0.0.1:{server.server_port}", "phi3.5", "PROMPT")
    finally:
        server.shutdown()
    assert out == ' {"intent": "x"}\n\n'
    assert seen["path"] == "/api/generate" and seen["model"] == "phi3.5" and seen["stream"] is False
    assert seen["options"]["temperature"] == 0 and seen["options"]["seed"] == 42
