"""Flask API bridge for the React SDN Impact Analyzer.

The React topology designer is stored separately from the live Mininet/Ryu
state. This prevents browser edits from overwriting topology discovered by Ryu.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from flask import Flask, jsonify, request
import networkx as nx
from impact_analyzer import ImpactAnalyzer
from mininet_runtime import runtime as mininet_runtime

BASE = Path(__file__).resolve().parent
LIVE_STATE_FILE = BASE / "network_state.json"
DESIGN_STATE_FILE = BASE / "designer_topology.json"
CONTROLLER_STATE_FILE = BASE / "controller_state.json"

app = Flask(__name__)


def _default_designer_state():
    if DESIGN_STATE_FILE.exists():
        return _read_json(DESIGN_STATE_FILE, {})
    live = _read_json(LIVE_STATE_FILE, {})
    devices = live.get("devices") or []
    links = live.get("device_links") or []
    if devices:
        return {"nodes": devices, "links": links}
    return {
        "nodes": [
            {"id": "h1", "type": "host", "label": "Host h1", "ip": "10.0.0.1/24"},
            {"id": "s1", "type": "switch", "label": "OpenFlow Switch s1", "control": "openflow", "openflow": "1.3"},
            {"id": "r1", "type": "router", "label": "Linux Router r1", "control": "linux-ip-forwarding"},
            {"id": "s2", "type": "switch", "label": "OpenFlow Switch s2", "control": "openflow", "openflow": "1.3"},
            {"id": "server", "type": "server", "label": "Server", "ip": "10.0.1.10/24"},
        ],
        "links": [
            {"source": "h1", "destination": "s1", "cableType": "ethernet"},
            {"source": "s1", "destination": "r1", "cableType": "ethernet"},
            {"source": "r1", "destination": "s2", "cableType": "ethernet"},
            {"source": "s2", "destination": "server", "cableType": "ethernet"},
        ],
    }


def _read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path: Path, data):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _reactflow_to_state(data):
    """Accept either {nodes, edges} from React Flow or {nodes, links}."""
    raw_nodes = data.get("nodes")
    raw_links = data.get("edges", data.get("links"))
    if not isinstance(raw_nodes, list) or not isinstance(raw_links, list):
        raise ValueError("Topology must include nodes and edges arrays.")

    nodes = []
    ids = set()
    for item in raw_nodes:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError("Every node must have a non-empty id.")
        node_id = str(item["id"])
        if node_id in ids:
            raise ValueError(f"Duplicate node id: {node_id}")
        ids.add(node_id)
        data_attrs = item.get("data") if isinstance(item.get("data"), dict) else {}
        kind = item.get("type") or data_attrs.get("deviceType") or "switch"
        attrs = {
            "id": node_id,
            "type": str(kind).lower(),
            "label": str(data_attrs.get("label") or item.get("label") or node_id),
            "status": data_attrs.get("status", "active"),
        }
        for key in ("ip", "gateway", "dpid", "openflow", "control", "interfaces", "mac", "subnet", "defaultRoute"):
            if key in data_attrs:
                attrs[key] = data_attrs[key]
        # Preserve additional runtime-relevant node properties without React Flow layout data.
        for key in ("gateway", "subnet", "defaultRoute"):
            if key in item and key not in attrs:
                attrs[key] = item[key]
        nodes.append(attrs)

    links = []
    seen = set()
    for index, item in enumerate(raw_links):
        if not isinstance(item, dict):
            raise ValueError(f"Link {index + 1} must be an object.")
        source = str(item.get("source") or "")
        target = str(item.get("target") or item.get("destination") or "")
        if source not in ids or target not in ids:
            raise ValueError(f"Link {index + 1} references a node that does not exist.")
        if source == target:
            raise ValueError("A device cannot be connected to itself.")
        pair = tuple(sorted((source, target)))
        if pair in seen:
            continue
        seen.add(pair)
        edge_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        links.append({
            "id": str(item.get("id") or f"link-{source}-{target}"),
            "source": source,
            "destination": target,
            "cableType": edge_data.get("cableType", item.get("cableType", "ethernet")),
            "label": str(edge_data.get("label") or item.get("label") or ""),
            "status": edge_data.get("status", "active"),
            "bandwidth": edge_data.get("bandwidth"),
            "delay": edge_data.get("delay"),
            "loss": edge_data.get("loss"),
            "delay": edge_data.get("delay"),
        })
    return {"nodes": nodes, "links": links}


def _load_designer_graph():
    state = _default_designer_state()
    graph = nx.Graph()
    for node in state.get("nodes", []):
        node_id = str(node.get("id"))
        if node_id and node_id != "None":
            graph.add_node(node_id, **{k: v for k, v in node.items() if k != "id"})
    for link in state.get("links", []):
        source = str(link.get("source") or link.get("src") or "")
        target = str(link.get("destination") or link.get("target") or "")
        if source in graph and target in graph:
            graph.add_edge(source, target, **{k: v for k, v in link.items()
                                               if k not in ("source", "destination", "target", "src")})
    return state, graph


def _topology_payload(state, graph):
    return {
        "nodes": [
            {"id": str(node), **dict(attrs)}
            for node, attrs in graph.nodes(data=True)
        ],
        "links": [
            {"id": attrs.get("id", f"link-{u}-{v}"),
             "source": str(u), "destination": str(v), **dict(attrs)}
            for u, v, attrs in graph.edges(data=True)
        ],
        "counts": {"devices": graph.number_of_nodes(), "links": graph.number_of_edges()},
    }


@app.after_request
def add_cors_headers(response):
    # Vite dev server normally runs on localhost:5173; allow local frontend dev.
    origin = request.headers.get("Origin", "")
    allowed = {"http://localhost:5173", "http://127.0.0.1:5173",
               "http://localhost:4173", "http://127.0.0.1:4173"}
    if origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    return response


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def options(_path):
    return ("", 204)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "Impact Network Analyzer API",
        "analysis_engine": "NetworkX",
        "mininet_runtime": mininet_runtime.status().get("running", False),
        "designer_topology_file": DESIGN_STATE_FILE.name,
        "live_mininet_state_file": LIVE_STATE_FILE.name,
    })


@app.get("/api/topology")
def get_topology():
    state, graph = _load_designer_graph()
    return jsonify(_topology_payload(state, graph))


@app.post("/api/topology")
def save_topology():
    try:
        state = _reactflow_to_state(request.get_json(silent=True) or {})
        # Validate the resulting graph before persisting.
        graph = nx.Graph()
        for node in state["nodes"]:
            graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
        for link in state["links"]:
            graph.add_edge(link["source"], link["destination"], **link)
        _write_json(DESIGN_STATE_FILE, state)
        return jsonify({"status": "saved", **_topology_payload(state, graph)})
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    failure_type = str(data.get("failure_type", "link")).lower()
    failed_element = data.get("failed_element")
    if failed_element is None or failed_element == "":
        return jsonify({"error": "failed_element is required"}), 400

    state, graph = _load_designer_graph()
    if failure_type == "link":
        # The frontend sends an edge id or {source,target}; resolve it to endpoints.
        if isinstance(failed_element, dict):
            source = str(failed_element.get("source", ""))
            target = str(failed_element.get("target", ""))
        elif isinstance(failed_element, (list, tuple)) and len(failed_element) == 2:
            source, target = map(str, failed_element)
        else:
            value = str(failed_element)
            matching = next((link for link in state["links"]
                             if str(link.get("id")) == value), None)
            if matching:
                source, target = matching["source"], matching["destination"]
            elif "-" in value:
                source, target = value.split("-", 1)
            else:
                return jsonify({"error": f"Could not resolve link: {value}"}), 400
        if not graph.has_edge(source, target):
            return jsonify({"error": f"Link {source} ↔ {target} does not exist."}), 400
        normalized_failure = [source, target]
    elif failure_type == "node":
        normalized_failure = str(failed_element)
        if normalized_failure not in graph:
            return jsonify({"error": f"Device {normalized_failure} does not exist."}), 400
    else:
        return jsonify({"error": "failure_type must be 'node' or 'link'"}), 400

    try:
        result = ImpactAnalyzer(graph).analyze(failure_type, normalized_failure).to_dict()
        result["failed_edge"] = normalized_failure if failure_type == "link" else None
        result["graph_summary"] = {
            "devices": graph.number_of_nodes(),
            "links": graph.number_of_edges(),
        }
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/reset")
def reset_analysis():
    return jsonify({"status": "reset"})


@app.post("/api/runtime/start")
def runtime_start():
    try:
        data = request.get_json(silent=True) or {}
        state = _reactflow_to_state(data)
        _write_json(DESIGN_STATE_FILE, state)
        result = mininet_runtime.start(
            state,
            controller_ip=str(data.get("controller_ip") or os.environ.get("RYU_CONTROLLER_IP", "127.0.0.1")),
            controller_port=int(data.get("controller_port") or os.environ.get("RYU_CONTROLLER_PORT", "6653")),
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/runtime/stop")
def runtime_stop():
    try:
        return jsonify(mininet_runtime.stop())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/runtime/status")
def runtime_status():
    result = mininet_runtime.status()
    controller_state = _read_json(CONTROLLER_STATE_FILE, {"running": False, "switches": [], "switch_count": 0, "event": "No Ryu state file yet"})
    try:
        with socket.create_connection(("127.0.0.1", 6653), timeout=0.25):
            controller_state["running"] = True
    except OSError:
        controller_state["running"] = False
        controller_state["switch_count"] = 0
        controller_state["switches"] = []
    result["controller_state"] = controller_state
    return jsonify(result)


@app.post("/api/runtime/pingall")
def runtime_pingall():
    try:
        return jsonify(mininet_runtime.ping_all())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/runtime/command")
def runtime_command():
    try:
        data = request.get_json(silent=True) or {}
        return jsonify(mininet_runtime.run_command(str(data.get("node") or ""), str(data.get("command") or "")))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/runtime/failure")
def runtime_failure():
    try:
        data = request.get_json(silent=True) or {}
        return jsonify(mininet_runtime.set_failure(str(data.get("kind") or ""), str(data.get("element") or ""), str(data.get("action") or "")))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
