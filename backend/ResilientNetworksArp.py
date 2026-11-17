"""Ryu controller for the Impact Network Analyzer.

The controller directly controls OpenFlow/OVS switches.  A Linux router and
server are represented in the project device model, while the Linux router
performs Layer-3 forwarding between the two IP networks.

Test topology:
    h1 -- s1 -- r1 -- s2 -- server
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4
from ryu.topology.api import get_switch, get_link, get_all_host
from ryu.topology import event as topo_event

import json
import os
import networkx as nx

from impact_analyzer import ImpactAnalyzer


class ResilientNetworkArp(app_manager.RyuApp):
    """Topology-aware OpenFlow forwarding and failure impact controller."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.topology_api_app = self

        # IMPORTANT: self.net is the OpenFlow switch graph used for routing.
        # Do not put the Linux router/server into this graph because OpenFlow
        # next-hop port lookup is defined only for OpenFlow switches.
        self.net = nx.DiGraph()
        self.links = {}

        # Project-level heterogeneous device graph.
        self.device_graph = nx.Graph()
        self.device_inventory_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "device_inventory.json"
        )
        self.device_inventory = self._load_device_inventory()

        # Learned forwarding state.
        self.mac_to_port = {}
        self.mac_to_dpid = {}
        self.ip_to_mac = {}

        self.state_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "network_state.json"
        )
        self.default_priority = 100

    # ---------- Device model ----------
    def _load_device_inventory(self):
        try:
            with open(self.device_inventory_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.logger.warning("[DEVICE] Could not load inventory: %s", exc)
            return {"devices": [], "links": []}

    def _router_interfaces(self):
        """Return configured Linux-router interfaces keyed by IP and MAC.

        These entries describe ports that are outside the OpenFlow topology.
        The controller uses them only to deliver Ethernet/ARP traffic to the
        correct switch port; Linux on r1 performs the actual IP routing.
        """
        result = {}
        for device in self.device_inventory.get("devices", []):
            if device.get("type") != "router":
                continue
            for intf in device.get("interfaces", []):
                ip = str(intf.get("ip", "")).split("/", 1)[0]
                mac = str(intf.get("mac", "")).lower()
                switch = str(intf.get("switch", ""))
                try:
                    switch_dpid = int(switch.lstrip("sS"))
                except ValueError:
                    switch_dpid = None
                port = intf.get("switch_port")
                if ip and mac and switch_dpid is not None and port is not None:
                    result[ip] = {
                        "router": str(device.get("id", "r1")),
                        "mac": mac,
                        "dpid": switch_dpid,
                        "port": int(port),
                        "interface": intf.get("name"),
                    }
                    result[mac] = result[ip]
        return result

    def _router_by_ip(self, ip):
        return self._router_interfaces().get(str(ip))

    def _router_by_mac(self, mac):
        return self._router_interfaces().get(str(mac).lower())

    def refresh_device_graph(self, switches=None):
        """Build a project-level graph containing switches, hosts, router and server.

        The static inventory describes devices that are not OpenFlow switches.
        Ryu's host discovery is then merged into the graph when available.
        """
        graph = nx.Graph()

        # Start with the explicit project inventory.
        for device in self.device_inventory.get("devices", []):
            device_id = str(device.get("id"))
            attrs = {k: v for k, v in device.items() if k != "id"}
            graph.add_node(device_id, **attrs)

        for u, v in self.device_inventory.get("links", []):
            graph.add_edge(str(u), str(v))

        # Replace switch metadata with the live OpenFlow DPID information.
        for sw in switches or []:
            sid = str(sw.dp.id)
            graph.add_node(sid, type="switch", control="openflow", dpid=sw.dp.id)

        # Add live host attachments discovered by Ryu.  This also allows the
        # model to grow when additional Mininet hosts are added later.
        try:
            for host in get_all_host(self.topology_api_app):
                mac = getattr(host, "mac", None)
                port = getattr(host, "port", None)
                if not mac or port is None:
                    continue
                host_id = str(mac)
                graph.add_node(host_id, type="host", mac=mac)
                graph.add_edge(host_id, str(port.dpid), port=port.port_no)
        except Exception as exc:
            self.logger.debug("[DEVICE] Host discovery unavailable: %s", exc)

        self.device_graph = graph
        return graph

    # ---------- Topology / impact analysis ----------
    def refresh_topology(self):
        switches = get_switch(self.topology_api_app, None)
        links = get_link(self.topology_api_app, None)

        graph = nx.DiGraph()
        graph.add_nodes_from(sw.dp.id for sw in switches)
        self.links = {}

        for link in links:
            graph.add_edge(link.src.dpid, link.dst.dpid, port=link.src.port_no)
            self.links[(link.src.dpid, link.dst.dpid)] = link.src.port_no

        self.net = graph
        self.refresh_device_graph(switches)
        return switches, links

    def export_network_state(self, last_result=None):
        try:
            device_nodes = []
            for node, attrs in self.device_graph.nodes(data=True):
                item = {"id": str(node)}
                item.update(attrs)
                device_nodes.append(item)

            device_links = []
            for u, v, attrs in self.device_graph.edges(data=True):
                item = {"source": str(u), "destination": str(v)}
                item.update(attrs)
                device_links.append(item)

            state = {
                # Backward-compatible OpenFlow switch graph.
                "nodes": [str(n) for n in self.net.nodes()],
                "links": [
                    [str(u), str(v)]
                    for u, v in self.net.to_undirected().edges()
                ],
                # New heterogeneous project graph.
                "devices": device_nodes,
                "device_links": device_links,
                "last_result": last_result,
            }

            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as exc:
            self.logger.warning("[IMPACT] Could not export network state: %s", exc)

    def analyze_failure(self, failure_type, failed_element):
        """Analyze an OpenFlow switch/link failure on the routing graph."""
        try:
            result = ImpactAnalyzer(self.net).analyze(
                failure_type, failed_element
            ).to_dict()
            self.export_network_state(result)
            self.logger.info(
                "[IMPACT] %s %s | score=%s severity=%s affected_nodes=%s disconnected_pairs=%s",
                failure_type,
                failed_element,
                result["impact_score"],
                result["severity"],
                len(result["affected_nodes"]),
                result["disconnected_pairs"],
            )
            return result
        except Exception as exc:
            self.logger.warning("[IMPACT] Analysis failed: %s", exc)
            return None

    def analyze_device_failure(self, failure_type, failed_element):
        """Analyze a failure in the heterogeneous device model.

        This is used for project-level simulation of hosts, routers and servers.
        Live OpenFlow link/switch events continue to use analyze_failure().
        """
        try:
            result = ImpactAnalyzer(self.device_graph).analyze(
                failure_type, failed_element
            ).to_dict()
            self.export_network_state(result)
            self.logger.info(
                "[DEVICE-IMPACT] %s %s | score=%s severity=%s",
                failure_type,
                failed_element,
                result["impact_score"],
                result["severity"],
            )
            return result
        except Exception as exc:
            self.logger.warning("[DEVICE-IMPACT] Analysis failed: %s", exc)
            return None

    @set_ev_cls(topo_event.EventSwitchEnter, MAIN_DISPATCHER)
    def switch_enter_handler(self, ev):
        self.refresh_topology()
        self.export_network_state()
        self.logger.info(
            "[TOPOLOGY] switches=%s links=%s",
            list(self.net.nodes()),
            list(self.net.edges()),
        )

    @set_ev_cls(topo_event.EventLinkAdd, MAIN_DISPATCHER)
    def link_add_handler(self, ev):
        self.refresh_topology()
        self.export_network_state()
        self.logger.info("[TOPOLOGY] link added; links=%s", list(self.net.edges()))

    @set_ev_cls(topo_event.EventLinkDelete, MAIN_DISPATCHER)
    def link_delete_handler(self, ev):
        link = ev.link
        failed_edge = (link.src.dpid, link.dst.dpid)
        self.logger.info(
            "[IMPACT] Link failure detected: %s-%s", *failed_edge
        )
        self.analyze_failure("link", failed_edge)
        self.refresh_topology()
        self.export_network_state()
        self._delete_ip_flows()

    @set_ev_cls(topo_event.EventSwitchLeave, MAIN_DISPATCHER)
    def switch_leave_handler(self, ev):
        dpid = ev.switch.dp.id
        self.logger.info("[IMPACT] Switch failure detected: %s", dpid)
        self.analyze_failure("node", dpid)
        self.refresh_topology()
        self.export_network_state()
        self._delete_ip_flows()

    # ---------- OpenFlow ----------
    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        kwargs = dict(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
        )
        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id
        datapath.send_msg(parser.OFPFlowMod(**kwargs))

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info(
            "[SWITCH %s] Default entry -TABLE MISS- initialized", datapath.id
        )

    def _delete_ip_flows(self):
        for dp in list(self._datapaths()):
            parser = dp.ofproto_parser
            ofproto = dp.ofproto
            match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP)
            mod = parser.OFPFlowMod(
                datapath=dp,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=match,
            )
            dp.send_msg(mod)

    def _datapaths(self):
        return [
            sw.dp for sw in get_switch(self.topology_api_app, None)
        ]

    # ---------- Packet processing ----------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        in_port = msg.match.get("in_port")

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        if eth.ethertype in (
            ether_types.ETH_TYPE_LLDP,
            ether_types.ETH_TYPE_IPV6,
        ):
            return

        src = eth.src
        dst = eth.dst
        self.mac_to_port.setdefault(datapath.id, {})[src] = in_port
        self.mac_to_dpid[src] = datapath.id

        # Refresh the live switch/device view before forwarding.
        self.refresh_topology()
        self.export_network_state()

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self.ip_to_mac[arp_pkt.src_ip] = src
            self.mac_to_port.setdefault(datapath.id, {})[src] = in_port

            if arp_pkt.opcode == arp.ARP_REQUEST:
                self._forward_arp_request(
                    datapath, in_port, msg.data, arp_pkt.dst_ip
                )
                return

            # ARP is Layer 2. Never build an IPv4 match for an ARP packet.
            self._forward_by_destination(
                datapath, in_port, msg.data, dst, destination_ip=None
            )
            return

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            self.ip_to_mac[ip_pkt.src] = src
            self._forward_by_destination(
                datapath,
                in_port,
                msg.data,
                dst,
                destination_ip=ip_pkt.dst,
            )

    def _forward_arp_request(self, datapath, in_port, data, target_ip):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # A Linux router is not an OpenFlow switch, so it is not returned by
        # get_all_host().  For configured router gateway IPs, answer ARP here
        # with the router interface MAC.  The resulting IP packet is then sent
        # by the switch to the router-facing port, where Linux performs routing.
        router = self._router_by_ip(target_ip)
        if router is not None:
            pkt = packet.Packet(data)
            eth_pkt = pkt.get_protocol(ethernet.ethernet)
            arp_pkt = pkt.get_protocol(arp.arp)
            if eth_pkt is not None and arp_pkt is not None:
                reply = packet.Packet()
                reply.add_protocol(ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_ARP,
                    dst=eth_pkt.src,
                    src=router["mac"],
                ))
                reply.add_protocol(arp.arp(
                    opcode=arp.ARP_REPLY,
                    src_mac=router["mac"],
                    src_ip=target_ip,
                    dst_mac=arp_pkt.src_mac,
                    dst_ip=arp_pkt.src_ip,
                ))
                reply.serialize()
                datapath.send_msg(parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=ofproto.OFPP_CONTROLLER,
                    actions=[parser.OFPActionOutput(in_port)],
                    data=reply.data,
                ))
                self.ip_to_mac[target_ip] = router["mac"]
                self.mac_to_port.setdefault(datapath.id, {})[router["mac"]] = router["port"]
                self.mac_to_dpid[router["mac"]] = datapath.id
                self.logger.info(
                    "[ARP] Proxy reply for router %s on switch %s port %s",
                    target_ip, datapath.id, router["port"]
                )
                return

        # If the target IP/MAC is already known, use normal destination routing.
        target_mac = self.ip_to_mac.get(target_ip)
        if target_mac:
            self._forward_by_destination(
                datapath, in_port, data, target_mac, destination_ip=None
            )
            return

        # Unknown ARP: use one BFS tree rooted at the ingress switch. This avoids
        # repeatedly circulating a broadcast around a ring.
        undirected = self.net.to_undirected()
        if datapath.id not in undirected:
            return

        tree = nx.bfs_tree(undirected, datapath.id)
        sent = False

        for child in tree.successors(datapath.id):
            port = self.net[datapath.id][child]["port"]
            if port == in_port:
                continue
            actions = [parser.OFPActionOutput(port)]
            datapath.send_msg(
                parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=in_port,
                    actions=actions,
                    data=data,
                )
            )
            sent = True

        # Send one copy to every non-switch-facing port. This includes Mininet
        # hosts and the Linux router interface attached to this switch.
        switch_obj = next(
            (
                s
                for s in get_switch(self.topology_api_app, None)
                if s.dp.id == datapath.id
            ),
            None,
        )
        switch_ports = {
            p.port_no for p in switch_obj.ports
        } if switch_obj else set()

        switch_link_ports = {
            self.net[datapath.id][n]["port"]
            for n in self.net.successors(datapath.id)
        }
        switch_link_ports |= {
            self.net[n][datapath.id]["port"]
            for n in self.net.predecessors(datapath.id)
        }

        for port in switch_ports - switch_link_ports - {in_port}:
            actions = [parser.OFPActionOutput(port)]
            datapath.send_msg(
                parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=ofproto.OFP_NO_BUFFER,
                    in_port=in_port,
                    actions=actions,
                    data=data,
                )
            )
            sent = True

        if sent:
            self.logger.info(
                "[ARP] Request for %s forwarded from switch %s",
                target_ip,
                datapath.id,
            )

    def _forward_by_destination(
        self,
        datapath,
        in_port,
        data,
        destination_mac,
        destination_ip=None,
    ):
        router = self._router_by_mac(destination_mac)
        if router is not None:
            if datapath.id != router["dpid"]:
                out_port = self.find_next_hop_to_destination(
                    datapath.id, router["dpid"]
                )
            else:
                out_port = router["port"]

            parser = datapath.ofproto_parser
            ofproto = datapath.ofproto
            if destination_ip is not None:
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_dst=destination_ip,
                )
            else:
                match = parser.OFPMatch(eth_dst=destination_mac)
            actions = [parser.OFPActionOutput(out_port)]
            self.add_flow(datapath, self.default_priority, match, actions)
            datapath.send_msg(parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=data,
            ))
            self.logger.info(
                "[ROUTE] switch %s -> Linux router %s via port %s",
                datapath.id, router["router"], out_port
            )
            return

        dst_dpid, dst_port = self.find_destination_switch(destination_mac)
        if dst_dpid is None:
            self.logger.info(
                "[ROUTE] Destination %s is not discovered yet",
                destination_mac,
            )
            return

        if dst_dpid == datapath.id:
            if dst_port is None:
                self.logger.info(
                    "[ROUTE] Destination %s has no learned port on switch %s",
                    destination_mac,
                    datapath.id,
                )
                return
            out_port = dst_port
        else:
            out_port = self.find_next_hop_to_destination(
                datapath.id, dst_dpid
            )

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # IPv4 packets can use an IP-destination flow. ARP uses Ethernet only.
        if destination_ip is not None:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_dst=destination_ip,
            )
        else:
            match = parser.OFPMatch(eth_dst=destination_mac)

        actions = [parser.OFPActionOutput(out_port)]
        self.add_flow(datapath, self.default_priority, match, actions)
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=data,
            )
        )
        self.logger.info(
            "[ROUTE] switch %s -> destination switch %s via port %s",
            datapath.id,
            dst_dpid,
            out_port,
        )

    # ---------- Host/path helpers ----------
    def find_destination_switch(self, destination_mac):
        # Live Ryu host discovery is preferred.
        try:
            for host in get_all_host(self.topology_api_app):
                if host.mac == destination_mac:
                    return host.port.dpid, host.port.port_no
        except Exception as exc:
            self.logger.debug("[HOST] get_all_host failed: %s", exc)

        # Learned MAC state is the fallback. This is important for the Linux
        # router interfaces because they are not OpenFlow switches themselves.
        if destination_mac in self.mac_to_dpid:
            dpid = self.mac_to_dpid[destination_mac]
            return dpid, self.mac_to_port.get(dpid, {}).get(destination_mac)

        return None, None

    def find_next_hop_to_destination(self, source_id, destination_id):
        self.refresh_topology()
        if source_id not in self.net or destination_id not in self.net:
            raise nx.NodeNotFound(
                f"{source_id} or {destination_id} not in topology"
            )
        path = nx.shortest_path(
            self.net,
            source=source_id,
            target=destination_id,
        )
        if len(path) < 2:
            raise nx.NetworkXNoPath
        return self.net[path[0]][path[1]]["port"]
