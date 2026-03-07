# CS4383 PA1 — Automated Grocery Ordering System

A distributed grocery ordering system using gRPC (Protobuf), ZMQ (FlatBuffers), Flask, and Streamlit.

## Components & Ports

| Service              | Protocol       | Port         | Description                               |
| -------------------- | -------------- | ------------ | ----------------------------------------- |
| `pricing_service`    | gRPC           | 50052        | Per-unit price lookup, returns total cost |
| `inventory_service`  | gRPC + ZMQ PUB | 50051 / 5556 | Manages stock, coordinates robot tasks    |
| `robot_service` (x5) | ZMQ SUB + gRPC | —            | One per aisle, fetches/restocks items     |
| `ordering_service`   | HTTP + ZMQ PUB | 5001 / 5557  | REST API, routes orders to inventory      |
| `client` (Streamlit) | HTTP           | 8501         | Browser UI for placing orders             |
| `analytics_service`  | ZMQ SUB        | —            | Collects latency/success stats (optional) |

## Prerequisites

- Python 3.10+
- `pip` (or a virtualenv)
- Ports **50051, 50052, 5001, 5556, 5557, 8501** open between VMs

---

## Setup (each VM)

```bash
cd ~/CS4383PA1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Proto `__init__.py` (required on every VM)

The `proto/` package needs an `__init__.py` that exposes the generated modules.
If it's missing or empty, create it:

```bash
cat > proto/__init__.py << 'PYEOF'
import importlib

def __getattr__(name):
    if name in (
        "common_pb2", "common_pb2_grpc",
        "ordering_inventory_pb2", "ordering_inventory_pb2_grpc",
        "robot_inventory_pb2", "robot_inventory_pb2_grpc",
        "inventory_pricing_pb2", "inventory_pricing_pb2_grpc",
    ):
        mod = importlib.import_module(f".{name}", __name__)
        globals()[name] = mod
        return mod
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
PYEOF
```

### FlatBuffers import patch (required on every VM)

The generated FlatBuffers code may use absolute imports that don't work from
the project root. Fix with:

```bash
sed -i 's/from grocery\.fb\.ItemQty import ItemQty/from .ItemQty import ItemQty/g' \
  fbschemas/grocery/fb/FetchTask.py fbschemas/grocery/fb/RestockTask.py
```

Or run `python3 scripts/patch_fbs_imports.py`.

### Generate protobuf stubs (only after `.proto` changes)

```bash
cd proto
python -m grpc_tools.protoc -I . --python_out=. common.proto
python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. \
  ordering_inventory.proto inventory_pricing.proto robot_inventory.proto
cd ..
```

Then fix imports in the generated `*_pb2*.py` files (change
`import common_pb2 as` to `from . import common_pb2 as`, etc.).

### Generate FlatBuffers stubs (only after `.fbs` changes)

```bash
cd fbschemas
flatc --python -o . common.fbs fetch.fbs restock.fbs analytics.fbs
cd ..
```

---

## Single-VM Quick Start

Run everything from the **repo root** (`~/CS4383PA1`), each in its own terminal:

```bash
# 1. Pricing (required by inventory)
python -m pricing_service.server

# 2. Inventory (starts ZMQ PUB on 5556)
python -m inventory_service.server

# 3. All 5 robots (background)
python -m robot_service.robot --aisle bread &
python -m robot_service.robot --aisle dairy &
python -m robot_service.robot --aisle meat &
python -m robot_service.robot --aisle produce &
python -m robot_service.robot --aisle party &

# 4. Ordering (HTTP 5001 + analytics PUB 5557)
python -m ordering_service.app

# 5. Analytics (optional)
python -m analytics_service.subscriber

# 6. Streamlit client (browser at http://localhost:8501)
streamlit run client/app.py --server.port 8501
```

---

## Multi-VM Setup (4 VMs)

### VM assignments

| VM      | IP           | Services                    |
| ------- | ------------ | --------------------------- |
| **VM1** | 172.16.5.77  | Ordering + Streamlit client |
| **VM2** | 172.16.5.69  | Inventory                   |
| **VM3** | 172.16.5.214 | Pricing + Analytics         |
| **VM4** | 172.16.5.58  | All 5 robots                |

### Network connections

| From → To                         | Address                 | Protocol |
| --------------------------------- | ----------------------- | -------- |
| Ordering (VM1) → Inventory (VM2)  | 172.16.5.69:50051       | gRPC     |
| Inventory (VM2) → Pricing (VM3)   | 172.16.5.214:50052      | gRPC     |
| Robots (VM4) → Inventory (VM2)    | 172.16.5.69:50051       | gRPC     |
| Robots (VM4) → Inventory (VM2)    | tcp://172.16.5.69:5556  | ZMQ SUB  |
| Analytics (VM3) → Ordering (VM1)  | tcp://172.16.5.77:5557  | ZMQ SUB  |
| Client (browser) → Ordering (VM1) | http://172.16.5.77:5001 | HTTP     |

PA2: All endpoints are configurable via environment variables (defaults above). Use env vars for K8s multi-cluster (NodePort) deployment.

### Setup on each VM

On **every VM**, clone the repo and install dependencies:

```bash
cd ~/CS4383PA1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then apply the proto `__init__.py` and FlatBuffers patches described above.

### Start order

Start services in this order so dependencies are ready:

#### 1. VM2 (172.16.5.69) — Inventory

```bash
cd ~/CS4383PA1
source .venv/bin/activate
python -m inventory_service.server
```

Listens on gRPC 50051 and ZMQ PUB 5556.

#### 2. VM3 (172.16.5.214) — Pricing + Analytics

**Terminal 1 — Pricing:**

```bash
cd ~/CS4383PA1
source .venv/bin/activate
python -m pricing_service.server
```

Listens on gRPC 50052.

**Terminal 2 — Analytics:**

```bash
cd ~/CS4383PA1
source .venv/bin/activate
python -m analytics_service.subscriber
```

Subscribes to VM1's ZMQ analytics stream (tcp://172.16.5.77:5557).

#### 3. VM4 (172.16.5.58) — All 5 robots

```bash
cd ~/CS4383PA1
source .venv/bin/activate
python -m robot_service.robot --aisle bread &
python -m robot_service.robot --aisle dairy &
python -m robot_service.robot --aisle meat &
python -m robot_service.robot --aisle produce &
python -m robot_service.robot --aisle party &
wait
```

Robots subscribe to VM2's ZMQ (tcp://172.16.5.69:5556) and report results via
gRPC to VM2 (172.16.5.69:50051).

To stop all robots: `pkill -f "robot_service.robot"`

#### 4. VM1 (172.16.5.77) — Ordering + Streamlit

**Terminal 1 — Ordering:**

```bash
cd ~/CS4383PA1
source .venv/bin/activate
python -m ordering_service.app
```

Listens on HTTP 5001 and ZMQ PUB 5557.

**Terminal 2 — Streamlit:**

```bash
cd ~/CS4383PA1
source .venv/bin/activate
streamlit run client/app.py --server.port 8501
```

Open **http://172.16.5.77:8501** in your browser.

---

## Pricing Model

Fixed per-unit prices (see `pricing_service/server.py`). Total = sum of
(unit_price × qty) for each item. Only charged for fulfilled quantities
(capped to available stock).

## Inventory Behavior

- Starts with **100 units** of each of the 25 items.
- **Grocery orders** (FETCH): requested quantities are capped to available stock.
  Items with 0 stock return qty 0 in the response.
- **Restock orders**: add to current stock (no cap).
- Stock persists in memory; restarting the inventory service resets to 100.

## Notes

- Run everything from the **repo root** so Python finds `proto/` and `fbschemas/`.
- Inventory waits up to 10s for all 5 robots to respond (barrier). Without all 5
  running, orders will timeout with partial results.
- Robots retry gRPC calls up to 3 times and survive errors (they don't crash on
  network hiccups).
- All services use insecure channels (no TLS). Use only in a controlled environment.

---

## PA2 Milestone 1: Deploy across K8s clusters (C2 + C3)

Deploy the app so the **end-to-end pipeline** works across clusters. **Remote services use NodePort** so pods in one cluster can reach another (e.g. robots on C3 talk to inventory on C2). For Milestone 1 you only need **C2** (core) and **C3** (robots); the client can run on your team VM or laptop.

### Cluster layout

| Cluster | Role | Services |
| ------- | ----- | -------- |
| **C2** | Core | Ordering, Inventory, Pricing, Analytics |
| **C3** | Warehouse | All 5 robots (bread, dairy, meat, produce, party) |
| **Client** | Your team VM or Mac | Streamlit (points at C2 ordering NodePort) |

Cluster master IPs: **C2=172.16.2.136**, **C3=172.16.3.137**. Deploy only in your team namespace (e.g. `team9`). This repo uses **team9** and **NodePorts in the 306xx range** to avoid conflicts with other teams.

### 1. SSH config (one-time, on your Mac)

You need **S26_BASTION.pem** (bastion) and **S26_CLUSTER.pem** (cluster masters). Put them in `~/.ssh/` with `chmod 0400`. Add to `~/.ssh/config`:

```
Host bastion
    User cc
    Hostname 129.114.25.220
    Port 22
    IdentityFile ~/.ssh/S26_BASTION.pem
    StrictHostKeyChecking no
    ForwardAgent yes

Host c2
    User cc
    Hostname 172.16.2.136
    Port 22
    ProxyJump bastion
    IdentityFile ~/.ssh/S26_CLUSTER.pem
    StrictHostKeyChecking no
    ForwardAgent yes

Host c3
    User cc
    Hostname 172.16.3.137
    Port 22
    ProxyJump bastion
    IdentityFile ~/.ssh/S26_CLUSTER.pem
    StrictHostKeyChecking no
    ForwardAgent yes
```

Then from your Mac: `ssh c2` and `ssh c3` land on the cluster masters.

### 2. Build and push images (from a machine that can reach the registry)

The private registry (e.g. **Reg2** `192.168.1.129:5000` for teams 6–10) is not reachable from a typical laptop. Use your **Chameleon team VM** (e.g. team9-vm1) where Docker can reach `192.168.1.129:5000`.

**On the team VM (e.g. team9-vm1):**

1. **Install Docker** (if not already):
   ```bash
   sudo apt-get update && sudo apt-get install -y docker.io
   sudo systemctl enable --now docker
   sudo usermod -aG docker cc
   ```
   Log out and back in so `docker` works without sudo.

2. **Allow insecure registry** (registry is HTTP):
   ```bash
   echo '{ "insecure-registries": ["192.168.1.129:5000"] }' | sudo tee /etc/docker/daemon.json
   sudo systemctl restart docker
   ```

3. **Generate protobuf stubs** and fix imports (required so containers can import `proto` as a package):
   ```bash
   cd ~/CS4383PA2
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cd proto
   python -m grpc_tools.protoc -I . --python_out=. common.proto
   python -m grpc_tools.protoc -I . --python_out=. --grpc_python_out=. \
     ordering_inventory.proto inventory_pricing.proto robot_inventory.proto
   cd ..
   # Fix absolute imports so they work inside the proto package
   sed -i 's/^import common_pb2 as/from . import common_pb2 as/' proto/ordering_inventory_pb2.py proto/ordering_inventory_pb2_grpc.py
   sed -i 's/^import common_pb2 as/from . import common_pb2 as/' proto/inventory_pricing_pb2.py proto/inventory_pricing_pb2_grpc.py
   sed -i 's/^import common_pb2 as/from . import common_pb2 as/' proto/robot_inventory_pb2.py proto/robot_inventory_pb2_grpc.py
   sed -i 's/^import ordering_inventory_pb2 as/from . import ordering_inventory_pb2 as/' proto/ordering_inventory_pb2_grpc.py
   sed -i 's/^import inventory_pricing_pb2 as/from . import inventory_pricing_pb2 as/' proto/inventory_pricing_pb2_grpc.py
   sed -i 's/^import robot_inventory_pb2 as/from . import robot_inventory_pb2 as/' proto/robot_inventory_pb2_grpc.py
   ```

4. **Build and push** (team9, Reg2):
   ```bash
   cd ~/CS4383PA2
   chmod +x scripts/build-and-push.sh
   ./scripts/build-and-push.sh 192.168.1.129:5000 team9
   ```

All images will be at `192.168.1.129:5000/team9/<service>:latest`.

### 3. Deploy on C2 (core services)

**From your Mac**, copy the repo to C2:

```bash
scp -r /path/to/CS4383PA2 c2:/home/cc/team9/CS4383PA2
```

**On C2** (`ssh c2`):

```bash
cd /home/cc/team9/CS4383PA2
kubectl apply -f k8s/namespace.yaml
kubectl config set-context --current --namespace=team9

kubectl apply -f k8s/pricing-service.yaml
kubectl apply -f k8s/inventory-service.yaml
kubectl apply -f k8s/ordering-service.yaml
kubectl apply -f k8s/analytics-service.yaml

kubectl get pods -n team9
```

Wait until `ordering-service`, `inventory-service`, `pricing-service`, and `analytics-service` are **1/1 Running**. If any Service fails with “port already allocated”, another team is using that NodePort; the repo uses **30601, 30651, 30656, 30652, 30657** for team9 to reduce conflicts.

**Team10 NodePorts on C2:**

| Service  | HTTP/gRPC | ZMQ  |
| -------- | --------- | ----- |
| Ordering | 30601     | 30657 |
| Inventory| 30651 (gRPC) | 30656 |
| Pricing  | 30652     | —     |

Health check: `curl http://localhost:30601/health` on C2 should return `{"status":"ok"}`.

### 4. Deploy robots on C3

**From your Mac**, copy the repo to C3:

```bash
scp -r /path/to/CS4383PA2 c3:/home/cc/team9/CS4383PA2
```

**On C3** (`ssh c3`):

```bash
cd /home/cc/team9/CS4383PA2
kubectl apply -f k8s/namespace.yaml
kubectl config set-context --current --namespace=team9
kubectl apply -f k8s/robots.yaml
kubectl get pods -n team9
```

All five robot pods should become **1/1 Running**. They connect to C2 inventory at `172.16.2.136:30651` (gRPC) and `172.16.2.136:30656` (ZMQ), as set in `k8s/robots.yaml`.

### 5. Run the client and verify end-to-end

Run the Streamlit client on your **team VM** or **Mac** (no need to use C1 for Milestone 1):

```bash
cd /path/to/CS4383PA2
source .venv/bin/activate   # if using venv
export ORDERING_HOST=172.16.2.136
export ORDERING_HTTP_PORT=30601
streamlit run client/app.py --server.port 8501
```

Open the URL shown (e.g. `http://<VM-IP>:8501`). Place a small grocery order (e.g. 1 bread, 1 milk) and submit. You should get a success response with items and optional total price.

**Verify in logs:**

- **C2** – `kubectl logs deploy/ordering-service -n team9 --tail=20`
- **C2** – `kubectl logs deploy/inventory-service -n team9 --tail=20`
- **C3** – `kubectl logs deploy/robot-bread -n team9 --tail=15`

You should see the order flow (HTTP → ordering → inventory → ZMQ to robots, robots report back, pricing, response). When this works, **Milestone 1 is complete**.

### Environment variables (reference)

| Variable | Used by | Meaning |
| -------- | ------- | ------- |
| `INVENTORY_HOST`, `INVENTORY_GRPC_PORT` | ordering, robots | Inventory (C2 IP + NodePort 30651) |
| `INVENTORY_ZMQ_PORT` | robots | Inventory ZMQ (30656) |
| `PRICING_HOST`, `PRICING_GRPC_PORT` | inventory | Pricing (same cluster: `pricing-service:50052`) |
| `ORDERING_HOST`, `ORDERING_HTTP_PORT` | client | Ordering HTTP (C2 IP + 30601) |
| `ORDERING_ZMQ_PORT`, `ORDERING_HOST` | analytics | Ordering ZMQ (same cluster: `ordering-service:5557`) |

---

## PA2 Milestone 2: Locust.io Workload Testing & Tail Latency Analysis

Use **Locust.io** to generate HTTP workloads simulating refrigerator (grocery order) and truck (restock) traffic, then measure **P50, P90, P95, P99 tail latencies** and plot **CDF curves**. No ContainerLab HIL is needed for this milestone.

### Prerequisites

Ensure services are deployed on C2 (core) and C3 (robots) from Milestone 1, and install the Locust dependency:

```bash
cd ~/CS4383PA2
source .venv/bin/activate
pip install -r requirements.txt     # includes locust, matplotlib, numpy
```

### SSH tunnel (if running Locust from your Mac)

C2 has no public IP. Set up a tunnel through the bastion so Locust can reach the ordering service NodePort:

```bash
ssh -L 30601:172.16.2.136:30601 bastion
```

Then use `http://localhost:30601` as the Locust target.

### 1. Run a single Locust scenario (interactive web UI)

```bash
cd ~/CS4383PA2
locust -f experiments/locustfile.py --host http://localhost:30601
```

Open **http://localhost:8089** in your browser. Set the number of users, spawn rate, and click **Start**.

### 2. Run a single scenario (headless — no web UI)

```bash
locust -f experiments/locustfile.py --host http://localhost:30601 \
    --headless -u 20 -r 5 -t 60s --csv experiments/results/my_test
```

### 3. Run the full experiment suite (5 scenarios)

```bash
chmod +x experiments/run_locust_experiments.sh
./experiments/run_locust_experiments.sh http://localhost:30601
```

This runs **low_load** (5 users), **medium_load** (20), **high_load** (50), **burst** (100), and **ramp_up** (50 users, slow spawn) in sequence. CSV data is saved to `experiments/results/<scenario>/`.

### 4. Analyze results and generate plots

```bash
python3 -m experiments.analyze_latencies
```

This reads the raw per-request latency CSVs and generates:

| Plot | Description |
| ---- | ----------- |
| `cdf_<scenario>.png` | CDF comparing refrigerator vs truck latency for each scenario |
| `cdf_compare_api_order.png` | CDF comparing refrigerator latency across all scenarios |
| `cdf_compare_api_restock.png` | CDF comparing truck latency across all scenarios |
| `percentile_bars_api_order.png` | P50/P90/P95/P99 bar chart for refrigerator requests |
| `percentile_bars_api_restock.png` | P50/P90/P95/P99 bar chart for truck requests |
| `cdf_combined_all.png` | Combined CDF for all scenarios |

All plots are saved to `experiments/plots/`.

### Workload design

| User class | Weight | Simulates | Request | Wait between requests |
| ---------- | ------ | --------- | ------- | --------------------- |
| `RefrigeratorUser` | 7 (70%) | Smart fridges | `POST /api/order` | 1–3 s |
| `TruckUser` | 3 (30%) | Delivery trucks | `POST /api/restock` | 2–5 s |

Refrigerators dominate traffic as specified in the assignment. Each grocery order randomly selects 1–10 items; each restock order selects 3–15 items with larger quantities.

### Experiment scenarios

| Scenario | Users | Spawn Rate | Duration | Purpose |
| -------- | ----- | ---------- | -------- | ------- |
| low_load | 5 | 1/s | 60s | Baseline |
| medium_load | 20 | 5/s | 90s | Moderate concurrency |
| high_load | 50 | 10/s | 120s | Stress test |
| burst | 100 | 50/s | 60s | Sudden spike |
| ramp_up | 50 | 1/s | 180s | Gradual increase |
