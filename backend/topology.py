"""Run the most recently saved React Flow topology directly in Mininet.

The Flask API uses the same MininetRuntime class. This CLI entry point is
provided for debugging without the browser:
    sudo .venv/bin/python topology.py [designer_topology.json]
Start Ryu first with start_ryu.sh.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet_runtime import MininetRuntime

BASE = Path(__file__).resolve().parent
json_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else BASE / "designer_topology.json"
with json_path.open("r", encoding="utf-8") as handle:
    topology_state = json.load(handle)

setLogLevel("info")
runtime = MininetRuntime()
runtime.start(topology_state)
try:
    CLI(runtime.net)
finally:
    runtime.stop()
