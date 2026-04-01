# PA3 Milestone 1 - ContainerLab1 (OSPF)

This folder replaces only ContainerLab1 from PA2 with a weighted OSPF WAN
topology while keeping the rest of PA2 unchanged.

## Topology

- Routers: `r1`..`r4` running FRR (`ospfd` + `zebra`)
- Entering LAN: `lan1` (with `ingress-host`, gateway at `r1`)
- Exiting LAN: `lan2` (with `egress-host`, gateway at `r4`)
- OSPF runs in Area 0 with loopback router-ids.
- LAN-facing interfaces are passive in OSPF.

Configured WAN costs:

- `r1-r2`: 100
- `r1-r3`: 10
- `r3-r2`: 10
- `r2-r4`: 10

Path comparison:

- Fewer hops but higher cost: `r1 -> r2 -> r4` (2 hops, total cost 110)
- More hops but lower cost: `r1 -> r3 -> r2 -> r4` (3 hops, total cost 30)

Expected best path is the lower total cost path via `r3`.

## One-time VM prep

Containerlab `kind: bridge` endpoints require Linux bridges on the VM:

```bash
sudo ip link add name lan1 type bridge 2>/dev/null || true
sudo ip link set lan1 up
sudo ip link add name lan2 type bridge 2>/dev/null || true
sudo ip link set lan2 up
```

## Run

```bash
cd ~/CS4383PA3/containerlab/hil1
./scripts/deploy_hil1.sh
```

## Milestone 1 Evidence Collection

Collect routing and OSPF state from every router (`r1`..`r4`):

```bash
cd ~/CS4383PA3/containerlab/hil1
./scripts/collect_ospf_state.sh
```

This script runs the required commands:

- `vtysh -c "show ip route"`
- `vtysh -c "show ip ospf neighbor"`
- `vtysh -c "show ip ospf database"`

Run traceroute from entering LAN to exiting LAN:

```bash
cd ~/CS4383PA3/containerlab/hil1
./scripts/traceroute_path.sh
```

Optional packet capture for Wireshark:

```bash
cd ~/CS4383PA3/containerlab/hil1
./scripts/capture_router_interface.sh r2 eth3 ./outputs/r2-eth3.pcap
```

Open `./outputs/*.pcap` in Wireshark on your machine.

## Optional VM static routes

If your PA2 deployment needs VM-level steering into LAN1/LAN2:

- Cluster 1 VM:
  - `sudo ip route replace 192.168.20.0/24 via 192.168.10.1`
- Cluster 2 VM:
  - `sudo ip route replace 192.168.10.0/24 via 192.168.20.1`

## Cleanup

```bash
cd ~/CS4383PA3/containerlab/hil1
./scripts/destroy_hil1.sh
```
