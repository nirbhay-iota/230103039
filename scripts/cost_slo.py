#!/usr/bin/env python3
"""Task 7: cost per 1,000 requests and SLO error budget, computed from a Locust run.

    python scripts/cost_slo.py --stats results/loadtest_stats.csv [--replicas 2] [--cpu-limit 1] [--mem-limit-gib 1]

Cost (rate card: data/rate_card.json): a replica is billed for its CPU limit and memory limit for every
hour it runs, whether or not it is busy.
    hourly cost of all replicas = replicas * (cpu_limit * vcpu_hour + mem_limit_gib * gib_memory_hour)
    requests per hour           = requests per second * 3600
    cost per 1,000 requests     = hourly cost / requests per hour * 1000
SLO: "SLO_TARGET % of requests in one load-test run succeed (HTTP 200 within 30 s)".
    error budget (requests) = total requests * (100 - target) / 100
    budget used             = failed requests / error budget
"""
import argparse
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def cost_per_1000(rps, replicas, cpu_limit, mem_limit_gib, card):
    hourly = replicas * (cpu_limit * card["vcpu_hour"] + mem_limit_gib * card["gib_memory_hour"])
    per_hour = rps * 3600
    return hourly, per_hour, hourly / per_hour * 1000


def error_budget(total, failed, target_percent):
    budget = total * (100 - target_percent) / 100
    return budget, failed, (failed / budget * 100 if budget else float("inf"))


def read_stats(path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    r = next(x for x in rows if x["Name"] == "Aggregated")
    return {"requests": int(r["Request Count"]), "failures": int(r["Failure Count"]), "rps": float(r["Requests/s"]),
            "p50": float(r["50%"]), "p95": float(r["95%"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stats", default="results/loadtest_stats.csv")
    ap.add_argument("--rate-card", default=str(ROOT / "data" / "rate_card.json"))
    ap.add_argument("--replicas", type=int, default=2)
    ap.add_argument("--cpu-limit", type=float, default=1.0, help="CPU limit per replica in cores (deployment.yaml)")
    ap.add_argument("--mem-limit-gib", type=float, default=1.0, help="memory limit per replica in GiB (deployment.yaml)")
    ap.add_argument("--slo-target", type=float, default=99.0)
    ap.add_argument("--out", default="results/cost_slo.md")
    a = ap.parse_args()

    card = json.load(open(a.rate_card))
    s = read_stats(a.stats)
    hourly, per_hour, cost = cost_per_1000(s["rps"], a.replicas, a.cpu_limit, a.mem_limit_gib, card)
    budget, failed, used = error_budget(s["requests"], s["failures"], a.slo_target)
    text = f"""# Cost and SLO (computed by scripts/cost_slo.py from {a.stats})

## Measured in the load test
- requests: {s['requests']}, failures: {s['failures']}, throughput: {s['rps']:.3f} requests/s
- latency p50: {s['p50']:.0f} ms, p95: {s['p95']:.0f} ms

## Cost per 1,000 requests ({card['currency']}, hypothetical rate card)
1. CPU cost per replica per hour = {a.cpu_limit} vCPU x {card['vcpu_hour']} = {a.cpu_limit * card['vcpu_hour']:.4f}
2. Memory cost per replica per hour = {a.mem_limit_gib} GiB x {card['gib_memory_hour']} = {a.mem_limit_gib * card['gib_memory_hour']:.4f}
3. Hourly cost of {a.replicas} replicas = {a.replicas} x ({a.cpu_limit * card['vcpu_hour']:.4f} + {a.mem_limit_gib * card['gib_memory_hour']:.4f}) = {hourly:.4f}
4. Requests served per hour = {s['rps']:.3f} x 3600 = {per_hour:.1f}
5. Cost per 1,000 requests = {hourly:.4f} / {per_hour:.1f} x 1000 = **{cost:.4f} {card['currency']}**

## SLO
- Objective: {a.slo_target:g}% of requests succeed (HTTP 200 within 30 s). Window: one load-test run ({s['requests']} requests).
- Error budget = {s['requests']} x (100 - {a.slo_target:g}) / 100 = **{budget:.1f} requests**
- Failed requests: {failed}. Budget used: {used:.1f}% ({'SLO met' if failed <= budget else 'SLO violated'}).
"""
    pathlib.Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
