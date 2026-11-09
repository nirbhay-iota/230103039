#!/usr/bin/env bash
set -euo pipefail
PIDFILE="${TMPDIR:-/tmp}/cc-mini-s3-pf.pid"
case "${1:-}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then exit 0; fi
    nohup kubectl -n data port-forward svc/seaweedfs 8333:8333 >/dev/null 2>&1 &
    echo $! > "$PIDFILE"
    for _ in $(seq 1 30); do
      if curl -s -o /dev/null http://localhost:8333; then exit 0; fi
      sleep 1
    done
    echo "port-forward did not come up" >&2; exit 1 ;;
  stop)
    if [ -f "$PIDFILE" ]; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; fi ;;
  *) echo "usage: $0 start|stop" >&2; exit 2 ;;
esac
