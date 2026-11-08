"""Unit tests for the Task 7 cost and SLO arithmetic."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import cost_slo  # noqa: E402

CARD = json.loads((ROOT / "data" / "rate_card.json").read_text())


def test_cost_formula_with_rate_card():
    hourly, per_hour, cost = cost_slo.cost_per_1000(rps=2.0, replicas=2, cpu_limit=1, mem_limit_gib=1, card=CARD)
    assert round(hourly, 4) == 7.9            # 2 x (1 x 3.50 + 1 x 0.45)
    assert per_hour == 7200
    assert round(cost, 4) == round(7.9 / 7200 * 1000, 4) == 1.0972


def test_error_budget():
    budget, failed, used = cost_slo.error_budget(total=1000, failed=4, target_percent=99)
    assert budget == 10 and failed == 4 and used == 40.0
