#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sudo apt update
sudo apt install -y python3 python3-venv python3-pip build-essential mininet openvswitch-switch
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r requirements.txt
sudo systemctl enable --now openvswitch-switch || true
sudo mn -c
printf '\nBase setup complete. Next, install a Ryu-compatible controller and run start_ryu.sh.\n'
