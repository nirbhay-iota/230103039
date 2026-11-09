set -euo pipefail
NS=app
HOST="${HOST:-http://localhost:8080}"
OUT="${OUT:-results/task4}"
mkdir -p "$OUT"

start_load() {
  local prefix="$1" runtime="$2" users="${3:-4}"
  LOADTEST_HEADERS_OUT="$OUT/${prefix}_headers.json" .venv/bin/locust -f tools/locustfile.py --headless \
    --users "$users" --spawn-rate "$users" --run-time "$runtime" --host "$HOST" \
    --csv "$OUT/$prefix" > "$OUT/${prefix}_locust.log" 2>&1 &
  LOAD_PID=$!
}

wait_load() { wait "$LOAD_PID" || true; }

load_summary() {
  python3 - "$1" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1] + "_stats.csv")))
r = next(x for x in rows if x["Name"] == "Aggregated")
n, f = int(r["Request Count"]), int(r["Failure Count"])
print(f"requests={n} failures={f} failure_percent={100*f/max(n,1):.3f} "
      f"p50_ms={r['50%']} p95_ms={r['95%']} rps={float(r['Requests/s']):.2f}")
PY
}

ready_count() { kubectl -n "$NS" get deploy parser -o jsonpath='{.status.readyReplicas}' 2>/dev/null | sed 's/^$/0/'; }

wait_ready() {
  local want="$1" t="${2:-600}" s=0
  until [ "$(ready_count)" = "$want" ] && [ "$(kubectl -n $NS get deploy parser -o jsonpath='{.status.replicas}')" = "$want" ]; do
    sleep 2; s=$((s + 2)); [ "$s" -ge "$t" ] && { echo "timeout waiting for $want ready replicas" >&2; return 1; }
  done
}
