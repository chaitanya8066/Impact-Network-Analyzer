"""Dynamic Mininet runtime for React Flow topologies.

Supported React node types: switch, host, server, router, cloud, controller.
- switch -> Open vSwitch (OpenFlow 1.3)
- host/server -> Mininet host
- router -> Linux host with IPv4 forwarding enabled
- cloud -> Mininet host (an endpoint placeholder)
- controller -> logical marker only; actual Ryu controller runs separately
"""
from __future__ import annotations

import ipaddress
import re
import threading
from typing import Any


class MininetRuntime:
    def __init__(self):
        self.net = None
        self.topology = None
        self.lock = threading.RLock()
        self.last_output = []
        self.controller_ip = "127.0.0.1"
        self.controller_port = 6653
        self.failed_links = set()
        self.failed_nodes = set()

    @staticmethod
    def _safe_name(value: str) -> str:
        original = str(value)
        value = re.sub(r"[^a-zA-Z0-9_]", "", original)
        if value != original or not value or not value[0].isalpha():
            raise ValueError(f"Invalid Mininet device name: {original!r}. Use letters, digits and underscores; start with a letter.")
        if len(value) > 12:
            raise ValueError(f"Device name '{value}' is too long (maximum 12 characters).")
        return value

    @staticmethod
    def _ip(value: str | None, index: int) -> str:
        if not value:
            return f"10.0.0.{index}/24"
        parsed = ipaddress.ip_interface(str(value) if "/" in str(value) else f"{value}/24")
        return str(parsed)

    def validate(self, state: dict[str, Any]) -> dict[str, Any]:
        nodes = state.get("nodes", [])
        links = state.get("links", [])
        if not nodes:
            raise ValueError("Add at least one device before starting Mininet.")
        if not isinstance(nodes, list) or not isinstance(links, list):
            raise ValueError("Topology must contain nodes and links arrays.")
        ids, normalized = set(), []
        host_index = 1
        for raw in nodes:
            node_id = self._safe_name(raw.get("id", ""))
            if node_id in ids:
                raise ValueError(f"Duplicate device id: {node_id}")
            ids.add(node_id)
            kind = str(raw.get("type", "switch")).lower()
            if kind not in {"switch", "host", "server", "router", "cloud", "controller"}:
                raise ValueError(f"Unsupported device type '{kind}' for {node_id}.")
            attrs = dict(raw)
            attrs["id"], attrs["type"] = node_id, kind
            if kind in {"host", "server", "router", "cloud"}:
                attrs["ip"] = self._ip(attrs.get("ip"), host_index)
                host_index += 1
            if kind == "switch":
                attrs["dpid"] = (re.sub(r"[^0-9a-fA-F]", "", str(attrs.get("dpid", ""))) or f"{len([n for n in normalized if n['type']=='switch'])+1:016x}").zfill(16)
                if len(attrs["dpid"]) > 16:
                    raise ValueError(f"Switch {node_id} DPID must be at most 16 hexadecimal digits.")
            normalized.append(attrs)
        valid_links = []
        for i, link in enumerate(links, 1):
            src = str(link.get("source") or link.get("src") or "")
            dst = str(link.get("destination") or link.get("target") or "")
            if src not in ids or dst not in ids:
                raise ValueError(f"Link {i} references a missing device ({src} -> {dst}).")
            if src == dst:
                raise ValueError(f"Link {i} cannot connect a device to itself.")
            if next(n for n in normalized if n['id'] == src)['type'] == 'controller' or next(n for n in normalized if n['id'] == dst)['type'] == 'controller':
                raise ValueError("The SDN Controller palette item is a logical marker. Connect data-plane devices to each other; Ryu is configured separately.")
            valid_links.append({**link, "source": src, "destination": dst})
        return {"nodes": normalized, "links": valid_links}

    def start(self, state: dict[str, Any], controller_ip="127.0.0.1", controller_port=6653):
        with self.lock:
            if self.net is not None:
                raise RuntimeError("A Mininet network is already running. Stop it before starting another topology.")
            state = self.validate(state)
            try:
                from mininet.net import Mininet
                from mininet.node import OVSSwitch, RemoteController, Host
                from mininet.link import TCLink
                from mininet.log import setLogLevel
            except Exception as exc:
                raise RuntimeError(f"Mininet is not available in this Python environment: {exc}") from exc

            class LinuxRouter(Host):
                def config(self, **params):
                    result = super().config(**params)
                    self.cmd("sysctl -w net.ipv4.ip_forward=1")
                    return result
                def terminate(self):
                    self.cmd("sysctl -w net.ipv4.ip_forward=0")
                    return super().terminate()

            setLogLevel("warning")
            net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, build=False, autoSetMacs=True)
            try:
                net.addController("c0", controller=RemoteController, ip=controller_ip, port=int(controller_port))
                node_by_id = {n["id"]: n for n in state["nodes"]}
                for node in state["nodes"]:
                    name, kind = node["id"], node["type"]
                    if kind == "controller":
                        continue
                    if kind == "switch":
                        net.addSwitch(name, cls=OVSSwitch, protocols="OpenFlow13", dpid=node.get("dpid"))
                    else:
                        cls = LinuxRouter if kind == "router" else Host
                        params = {"ip": node["ip"]}
                        if node.get("mac"):
                            params["mac"] = node["mac"]
                        net.addHost(name, cls=cls, **params)
                for link in state["links"]:
                    src, dst = link["source"], link["destination"]
                    a, b = node_by_id[src], node_by_id[dst]
                    cable = str((link.get("data") or {}).get("cableType") or link.get("cableType") or "ethernet").lower()
                    bw = 10000 
                    params = {"bw": bw}
                    data = link.get("data") or {}
                    if data.get("delay"):
                        params["delay"] = str(data["delay"])
                    if data.get("loss") is not None:
                        params["loss"] = float(data["loss"])
                    net.addLink(src, dst, **params)
                net.build()
                net.start()
                self.net, self.topology = net, state
                self.failed_links.clear()
                self.failed_nodes.clear()
                self.controller_ip, self.controller_port = controller_ip, int(controller_port)
                self.last_output = [f"Created {len(state['nodes'])} devices and {len(state['links'])} links.",
                                    f"Remote Ryu controller: {controller_ip}:{controller_port}",
                                    "Mininet network started."]
                return self.status()
            except Exception:
                try:
                    net.stop()
                except Exception:
                    pass
                raise

    def stop(self):
        with self.lock:
            if self.net is None:
                return {"running": False, "output": ["No Mininet network is running."]}
            try:
                self.net.stop()
                self.last_output = ["Mininet network stopped and cleaned up."]
            finally:
                self.net = None
                self.topology = None
                self.failed_links.clear()
                self.failed_nodes.clear()
            return {"running": False, "output": self.last_output}

    def status(self):
        with self.lock:
            if self.net is None:
                return {"running": False, "nodes": [], "links": [], "output": self.last_output}
            nodes = []
            types = {item["id"]: item["type"] for item in self.topology["nodes"]}
            for name, node in self.net.nameToNode.items():
                if name == "c0":
                    continue
                nodes.append({"id": name, "type": types.get(name, "host"),
                              "status": "down" if name in self.failed_nodes else "up"})
            links = []
            for link in self.topology["links"]:
                link_id = link.get("id") or f"link-{link['source']}-{link['destination']}"
                pair = tuple(sorted((link["source"], link["destination"])))
                links.append({"id": link_id, "source": link["source"], "target": link["destination"],
                              "status": "down" if pair in self.failed_links else "up"})
            return {"running": True, "nodes": nodes, "links": links, "output": self.last_output,
                    "controller": {"ip": self.controller_ip, "port": self.controller_port}}

    def ping_all(self):
        with self.lock:
            if self.net is None:
                raise RuntimeError("Start the Mininet topology first.")
            output = self.net.pingAll()
            self.last_output = [f"Mininet pingAll packet-loss result: {output}% packet loss"]
            return {"packet_loss_percent": output, "output": self.last_output}

    def run_command(self, node_name: str, command: str):
        with self.lock:
            if self.net is None:
                raise RuntimeError("Start the Mininet topology first.")
            if node_name not in self.net.nameToNode or node_name == "c0":
                raise ValueError(f"Unknown Mininet node: {node_name}")
            allowed = ("ping ", "ping6 ", "ip addr", "ip route", "ip link", "ifconfig", "route", "arp", "ethtool ")
            cmd = command.strip()
            if any(token in cmd for token in (";", "|", "&", "`", "$", "\n", "\r", ">", "<")):
                raise ValueError("Shell operators and command chaining are not allowed.")
            if not any(cmd == item or cmd.startswith(item) for item in allowed):
                raise ValueError("Command not allowed. Use ping, ip addr/route/link, ifconfig, route, arp or ethtool.")
            result = self.net.get(node_name).cmd(cmd)
            self.last_output = [f"{node_name}$ {cmd}", result.strip()]
            return {"node": node_name, "command": cmd, "output": result}

    def set_failure(self, kind: str, element: str, action: str):
        with self.lock:
            if self.net is None:
                raise RuntimeError("Start the Mininet topology first.")
            if action not in {"down", "up"}:
                raise ValueError("action must be 'down' or 'up'.")
            if kind == "link":
                match = next((x for x in self.topology["links"] if x.get("id") == element or f"link-{x['source']}-{x['destination']}" == element), None)
                if not match:
                    raise ValueError(f"Unknown link: {element}")
                self.net.configLinkStatus(match["source"], match["destination"], action)
                pair = tuple(sorted((match["source"], match["destination"])))
                if action == "down": self.failed_links.add(pair)
                else: self.failed_links.discard(pair)
                message = f"Link {match['source']} ↔ {match['destination']} set {action.upper()}"
            elif kind == "node":
                if element not in self.net.nameToNode or element == "c0":
                    raise ValueError(f"Unknown node: {element}")
                node = self.net.get(element)
                if types_is_switch(self.topology, element):
                    if action == "down":
                        node.stop()
                    else:
                        node.start([self.net.get("c0")])
                else:
                    for intf in list(node.intfList()):
                        node.cmd(f"ip link set dev {intf.name} {'down' if action == 'down' else 'up'}")
                if action == "down": self.failed_nodes.add(element)
                else: self.failed_nodes.discard(element)
                message = f"Node {element} set {action.upper()}"
            else:
                raise ValueError("kind must be node or link")
            self.last_output = [message]
            return {"output": self.last_output, "status": self.status()}


def types_is_switch(state, node_id):
    return any(item["id"] == node_id and item["type"] == "switch" for item in state.get("nodes", []))


runtime = MininetRuntime()
