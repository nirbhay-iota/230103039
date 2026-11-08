"""Unit tests for Task 5: subnet plan and NACL rules."""
import ipaddress
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import nacl_sim  # noqa: E402


def allocate(block, needs):
    cur = int(ipaddress.ip_network(block).network_address)
    out = {}
    for name, hosts in needs:
        prefix = 32 - math.ceil(math.log2(hosts + 2))
        net = ipaddress.ip_network((cur, prefix))
        out[name] = net
        cur += net.num_addresses
    return out


def test_subnet_plan():
    plan = allocate("10.20.0.0/16", [("app", 1000), ("public", 250), ("data", 100), ("management", 20)])
    assert str(plan["app"]) == "10.20.0.0/22"
    assert str(plan["public"]) == "10.20.4.0/24"
    assert str(plan["data"]) == "10.20.5.0/25"
    assert str(plan["management"]) == "10.20.5.128/27"
    assert [n.num_addresses - 2 for n in plan.values()] == [1022, 254, 126, 30]


def _decide(rules, direction, port, address, protocol="tcp"):
    pkt = {"direction": direction, "protocol": protocol, "port": port, "address": address}
    return nacl_sim.decide(rules, pkt)[0]


def test_sample_packets_all_correct():
    rules = nacl_sim.load_rules(ROOT / "network" / "nacl.json")
    for line in (ROOT / "network" / "packets_sample.jsonl").read_text().splitlines():
        p = json.loads(line)
        assert nacl_sim.decide(rules, p)[0] == p["expected"], p["id"]


def test_abusive_range_blocked_even_on_web_ports():
    rules = nacl_sim.load_rules(ROOT / "network" / "nacl.json")
    for port in (80, 443, 22, 40000):
        assert _decide(rules, "inbound", port, "198.51.100.77") == "deny"
    assert _decide(rules, "inbound", 443, "198.51.101.1") == "allow"


def test_ssh_only_from_management_and_replies_from_app_only():
    rules = nacl_sim.load_rules(ROOT / "network" / "nacl.json")
    assert _decide(rules, "inbound", 22, "10.20.5.130") == "allow"
    assert _decide(rules, "inbound", 22, "10.20.5.20") == "deny"
    assert _decide(rules, "inbound", 40000, "10.20.2.9") == "allow"
    assert _decide(rules, "inbound", 40000, "203.0.113.9") == "deny"


def test_deny_rule_number_is_below_allow_rules():
    data = json.loads((ROOT / "network" / "nacl.json").read_text())
    deny = min(r["rule"] for r in data["inbound"] if r["action"] == "deny")
    allows = [r["rule"] for r in data["inbound"] if r["action"] == "allow"]
    assert deny < min(allows)
