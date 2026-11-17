# SDN Impact Analyzer — React + Dynamic Mininet + Ryu

This package preserves the React Flow frontend and adds a dynamic Mininet runtime. The backend receives the **current topology drawn in the browser** as JSON and creates a real Mininet network from it. It is not limited to the old hardcoded `h1-s1-r1-s2-server` example.

## What is implemented

- React Flow topology editor remains the source of truth for the drawn topology.
- The current nodes and edges are sent to Flask as JSON when **Start current topology** is pressed.
- Flask validates device IDs, device types, link endpoints and IP addresses.
- Mininet devices are created dynamically:
  - `switch` → Open vSwitch with OpenFlow 1.3
  - `host` → Mininet host
  - `server` → Mininet host endpoint
  - `router` → Linux host with IPv4 forwarding enabled
  - `cloud` → Mininet host endpoint placeholder
  - `controller` → logical canvas marker only; Ryu is a separate controller process
- Ryu app included: `backend/impact_controller.py` (OpenFlow 1.3 learning switch, switch connection and port-status logging).
- Live Mininet panel: start/stop, `pingAll`, node/link down/up, selected-node diagnostics and returned terminal output.
- NetworkX failure-impact analysis remains available separately in the Impact Analysis section.

## Important behavior and limits

1. The Ryu controller must be started **before** starting Mininet. Default controller endpoint is `127.0.0.1:6653` from inside the Ubuntu VM.
2. The `controller` palette object is a visual/logical marker. Do not connect it as a data-plane device. Ryu runs outside Mininet and controls OVS switches over OpenFlow.
3. A `cloud` node is represented as a Mininet host endpoint, not a real Internet/cloud gateway.
4. `router` nodes enable Linux IPv4 forwarding. For multi-subnet routing, configure appropriate interface IPs and routes; the current visual property panel only exposes a single IP field, so the default auto-addressing is intended for simple lab topologies.
5. Fiber/ethernet labels are mapped to Mininet TCLink bandwidth values (10,000/1,000 Mbps). These are emulated link settings, not physical throughput guarantees.
6. The browser cannot execute Mininet directly. Mininet and Flask must run inside Linux with the required privileges. This project uses the Ubuntu VM as the execution host.
7. This source package has been syntax-checked, but live Mininet/Ryu execution and a full browser build have **not** been verified in your VM yet. We must test there after setup.

## Windows + VirtualBox NAT arrangement

- React frontend runs on Windows at `http://localhost:5173`.
- Flask API runs inside Ubuntu VM on port `5000`.
- Add VirtualBox NAT port forwarding: Host IP `127.0.0.1`, Host Port `5000`, Guest Port `5000`, Protocol TCP.
- The frontend default API URL is `http://127.0.0.1:5000`.
- Ryu port `6653` is only needed between Ryu and Mininet inside Ubuntu; it does not need host forwarding.

## Ubuntu 25.04 setup (existing VM)

Do not create another VM for this package. In Ubuntu, open a terminal and run:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential mininet openvswitch-switch
```

Copy the `backend` folder into Ubuntu, then:

```bash
cd backend
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl enable --now openvswitch-switch
sudo mn -c
sudo mn --test pingall
```

The Mininet smoke test should complete successfully before starting the application.

### Ryu installation

Ryu packaging may need extra compatibility work on newer Python versions. First check:

```bash
python3 --version
```

Then try installing Ryu in the backend virtual environment:

```bash
.venv/bin/python -m pip install ryu
```

If pip fails on Ubuntu 25.04/Python 3.13, stop and share the **full error output** rather than forcing dependency upgrades. We will choose a compatible Ryu-compatible controller package/runtime based on the exact error. Do not install random system-wide Python packages.

### Start Ryu (Ubuntu terminal 1)

```bash
cd backend
./start_ryu.sh
```

Expected: Ryu starts listening on TCP port `6653`. Keep this terminal open.

### Start Flask API (Ubuntu terminal 2)

Mininet requires root privileges. Run:

```bash
cd backend
sudo .venv/bin/python dashboard.py
```

Expected: Flask listens on `0.0.0.0:5000`.

### Start React frontend (Windows PowerShell)

```powershell
cd path\to\frontend
npm install
npm run dev
```

Open the Vite URL, draw/connect your devices, then use **Live Mininet → Start current topology**.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Backend health |
| POST | `/api/topology` | Save React Flow topology JSON |
| POST | `/api/runtime/start` | Build and start dynamic Mininet network |
| POST | `/api/runtime/stop` | Stop and clean up Mininet |
| GET | `/api/runtime/status` | Current runtime state |
| POST | `/api/runtime/pingall` | Run Mininet pingAll |
| POST | `/api/runtime/command` | Run an allow-listed diagnostic command on a Mininet node |
| POST | `/api/runtime/failure` | Bring a node/link down or restore it |
| POST | `/api/analyze` | NetworkX topology failure-impact analysis |

## JSON model

The frontend sends React Flow's `{ "nodes": [...], "edges": [...] }`. Each node's `id`, `type`, and `data` are used. Each edge's `source`, `target`, and `data.cableType` are used. Canvas coordinates and styling are ignored by Mininet.

Example node:

```json
{
  "id": "s1",
  "type": "switch",
  "position": { "x": 200, "y": 120 },
  "data": { "label": "Core switch", "dpid": "0001", "openflow": "1.3" }
}
```

Example link:

```json
{
  "id": "link-s1-h1",
  "source": "s1",
  "target": "h1",
  "data": { "cableType": "ethernet", "status": "active" }
}
```

## Cleanup

Stop the network using the Live Mininet panel or call `/api/runtime/stop`. If a previous run was interrupted:

```bash
sudo mn -c
```

Do not expose the Flask API to an untrusted network. It is a local lab control API and should remain behind VirtualBox NAT/localhost forwarding.
