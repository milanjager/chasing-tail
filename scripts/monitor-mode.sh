#!/usr/bin/env bash
# Přepne Wi-Fi adaptér do monitor mode. Použití: monitor-mode.sh wlan1
set -euo pipefail
IFACE="${1:-wlan1}"

if ! ip link show "$IFACE" >/dev/null 2>&1; then
  echo "Rozhraní $IFACE neexistuje – je USB Wi-Fi adaptér připojený?" >&2
  exit 1
fi

command -v nmcli >/dev/null && nmcli device set "$IFACE" managed no || true
ip link set "$IFACE" down
iw dev "$IFACE" set type monitor
ip link set "$IFACE" up
echo "$IFACE je v monitor mode"
