#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ -x ryu-env/bin/ryu-manager ]]; then
  exec ryu-env/bin/ryu-manager --ofp-tcp-listen-port 6653 impact_controller.py
fi

echo "Ryu manager not found in ryu-env." >&2
exit 1
