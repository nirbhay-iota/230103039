# Task 5: Subnet allocation and NACL

Address block: `10.20.0.0/16`. Subnets are allocated from the largest requirement
to the smallest, each placed immediately after the previous one, using the smallest
prefix that fits (`usable hosts = 2^(32-prefix) - 2`).

## Working

| Subnet     | Hosts needed | Host bits h with 2^h - 2 >= need | Prefix | Usable hosts |
|------------|-------------:|----------------------------------|-------:|-------------:|
| app        | 1,000        | h = 10 (2^10 - 2 = 1,022; h = 9 gives only 510) | /22 | 1,022 |
| public     | 250          | h = 8 (2^8 - 2 = 254; h = 7 gives only 126)     | /24 | 254   |
| data       | 100          | h = 7 (2^7 - 2 = 126; h = 6 gives only 62)      | /25 | 126   |
| management | 20           | h = 5 (2^5 - 2 = 30; h = 4 gives only 14)       | /27 | 30    |

Block sizes are 1,024, 256, 128 and 32 addresses. Starting at `10.20.0.0`:

- app: `10.20.0.0` + 1,024 addresses ends at `10.20.3.255`; next free address is `10.20.4.0`
- public: `10.20.4.0` + 256 ends at `10.20.4.255`; next free address is `10.20.5.0`
- data: `10.20.5.0` + 128 ends at `10.20.5.127`; next free address is `10.20.5.128`
- management: `10.20.5.128` + 32 ends at `10.20.5.159`; next free address is `10.20.5.160`

Each network address is a multiple of its block size (a requirement for a valid CIDR block),
so no padding is needed between the blocks.

## Result

| Subnet     | Network address | Prefix | Usable host range         | Broadcast address | Usable hosts |
|------------|-----------------|-------:|---------------------------|-------------------|-------------:|
| app        | 10.20.0.0       | /22    | 10.20.0.1 - 10.20.3.254   | 10.20.3.255       | 1,022        |
| public     | 10.20.4.0       | /24    | 10.20.4.1 - 10.20.4.254   | 10.20.4.255       | 254          |
| data       | 10.20.5.0       | /25    | 10.20.5.1 - 10.20.5.126   | 10.20.5.127       | 126          |
| management | 10.20.5.128     | /27    | 10.20.5.129 - 10.20.5.158 | 10.20.5.159       | 30           |

## NACL for the public subnet (`network/nacl.json`)

Rules are evaluated from the lowest number upward; the first match decides; no match means deny.

Inbound:

| Rule | Action | Protocol / ports | Source CIDR       | Purpose |
|-----:|--------|------------------|-------------------|---------|
| 100  | deny   | all              | 198.51.100.0/24   | abusive range, blocked even on web ports |
| 110  | allow  | tcp 80           | 0.0.0.0/0         | HTTP |
| 120  | allow  | tcp 443          | 0.0.0.0/0         | HTTPS |
| 130  | allow  | tcp 22           | 10.20.5.128/27    | SSH from the management subnet only |
| 140  | allow  | tcp 1024-65535   | 10.20.0.0/22      | replies from the app subnet to the load balancer's ephemeral ports |
| *    | deny   | all              | any               | implicit default |

Outbound:

| Rule | Action | Protocol / ports | Destination CIDR  | Purpose |
|-----:|--------|------------------|-------------------|---------|
| 100  | allow  | tcp 8000         | 10.20.0.0/22      | load balancer to the service in the app subnet |
| 110  | allow  | tcp 1024-65535   | 0.0.0.0/0         | replies back to clients (ephemeral ports) |
| *    | deny   | all              | any               | implicit default |

Check: `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check`
(output saved in `results/nacl_check.txt`).

## Why replies need their own rules, and why rule order matters

A network ACL is stateless: it looks at every packet on its own and keeps no table of
connections. A security group would automatically admit the reply to an allowed request, but a
NACL does not, so the reply to a client's request on TCP 443 is a fresh outbound packet that
must be allowed explicitly. That is why outbound rule 110 allows the ephemeral ports
1024-65535 towards any client. In the other direction, the load balancer opens connections to
the app subnet on port 8000 (outbound rule 100), and the responses come back inbound to the
load balancer's ephemeral ports, which inbound rule 140 allows, but only from the app subnet.

Order matters because the first matching rule wins. The deny for `198.51.100.0/24` is rule 100,
which is lower than the allow rules for ports 80 and 443 (110 and 120). A packet from
198.51.100.9 to port 443 therefore matches the deny first and is dropped. If the deny were
numbered above 120, the "allow tcp 443 from anywhere" rule would match first, the deny would
never be reached, and the abusive range would get through.
