"""Ryu OpenFlow 1.3 learning controller for the generated Mininet topology.
Run with: ryu-manager --ofp-tcp-listen-port 6653 impact_controller.py
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub
import json
import os
import tempfile
from pathlib import Path


class ImpactController13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.state_file = Path(os.environ.get("SDN_CONTROLLER_STATE", Path(__file__).with_name("controller_state.json")))
        self.port_state = {}
        self.monitor_thread = hub.spawn(self._monitor)
        self._write_state("Controller started")
        self.logger.info("SDN Impact Analyzer Ryu controller started (OpenFlow 1.3)")

    def _write_state(self, event):
        state = {"running": True, "event": str(event),
                 "switches": [{"dpid": f"{dpid:016x}", "connected": True,
                               "ports": self.port_state.get(dpid, [])}
                              for dpid in sorted(self.datapaths)],
                 "switch_count": len(self.datapaths)}
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=str(self.state_file.parent), prefix="controller-")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2)
            os.replace(temp_name, self.state_file)
        except OSError as exc:
            self.logger.warning("Could not write controller state: %s", exc)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, 0, match, actions)
        self._write_state(f"Switch connected: {dp.id:016x}")
        self.logger.info("Switch connected: dpid=%016x", dp.id)

    def add_flow(self, dp, priority, match, actions, buffer_id=None):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        instructions = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        kwargs = {"datapath": dp, "priority": priority, "match": match, "instructions": instructions}
        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id
        dp.send_msg(parser.OFPFlowMod(**kwargs))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        dpid = dp.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port
        out_port = self.mac_to_port[dpid].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst, eth_src=eth.src)
            self.add_flow(dp, 1, match, actions, msg.buffer_id if msg.buffer_id != ofp.OFP_NO_BUFFER else None)
            if msg.buffer_id != ofp.OFP_NO_BUFFER:
                return
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id,
                                       in_port=in_port, actions=actions, data=data))

    @set_ev_cls(ofp_event.EventOFPPortStatus, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def port_status_handler(self, ev):
        msg = ev.msg
        self.logger.warning("Port status event: dpid=%016x reason=%s port=%s",
                            msg.datapath.id, msg.reason, msg.desc.port_no)
        self._write_state(f"Port status event on {msg.datapath.id:016x}, port {msg.desc.port_no}")

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def state_change_handler(self, ev):
        dp = ev.datapath

        if dp.id is None:
            self.logger.warning("Ignoring state change event with no datapath ID")
            return

        if ev.state == MAIN_DISPATCHER:
            self.datapaths[dp.id] = dp
        elif ev.state == CONFIG_DISPATCHER:
            self.datapaths.pop(dp.id, None)

        self._write_state(
            f"Datapath state changed: {dp.id:016x} -> {ev.state}"
        )

    def _monitor(self):
        while True:
            for dp in list(self.datapaths.values()):
                parser = dp.ofproto_parser
                dp.send_msg(parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            hub.sleep(10)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dp = ev.msg.datapath
        self.port_state[dp.id] = [{"port_no": stat.port_no, "rx_packets": stat.rx_packets,
                                   "tx_packets": stat.tx_packets, "rx_bytes": stat.rx_bytes,
                                   "tx_bytes": stat.tx_bytes} for stat in ev.msg.body]
        self._write_state(f"Received port statistics from {dp.id:016x}")
