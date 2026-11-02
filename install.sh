#!/usr/bin/env bash
# Instalace Chasing Your Tail na Raspberry Pi OS (Bookworm, 64-bit).
# Spuštění:  sudo ./install.sh
set -euo pipefail

APP_DIR=/opt/chasing-tail
DATA_DIR=/var/lib/chasing-tail
LOG_DIR=/var/log/chasing-tail

if [[ $EUID -ne 0 ]]; then
  echo "Spusťte přes sudo." >&2
  exit 1
fi

echo "==> Systémové balíčky"
apt-get update
apt-get install -y rsync python3-venv python3-dev iw wireless-tools bluez gpsd gpsd-clients libpcap0.8

echo "==> Kopírování aplikace do $APP_DIR"
mkdir -p "$APP_DIR" "$DATA_DIR" "$LOG_DIR"
rsync -a --delete --exclude '.git' --exclude '__pycache__' --exclude 'config.local.yaml' ./ "$APP_DIR/"
chmod +x "$APP_DIR/scripts/"*.sh

echo "==> Python prostředí"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/config.local.yaml" ]]; then
  PASS=$(head -c 12 /dev/urandom | base64 | tr -d '/+=')
  cat > "$APP_DIR/config.local.yaml" <<EOF
# Lokální nastavení – přepisuje config.yaml
gps:
  device: gpsd
web:
  password: "$PASS"
EOF
  chmod 600 "$APP_DIR/config.local.yaml"
  echo "    Heslo k dashboardu (uživatel admin): $PASS"
  echo "    Uloženo v $APP_DIR/config.local.yaml"
fi

echo "==> GPS (gpsd)"
GPS_DEV=$(ls /dev/ttyACM0 /dev/ttyUSB0 2>/dev/null | head -n1 || true)
if [[ -n "$GPS_DEV" ]]; then
  sed -i "s|^DEVICES=.*|DEVICES=\"$GPS_DEV\"|; s|^GPSD_OPTIONS=.*|GPSD_OPTIONS=\"-n\"|" /etc/default/gpsd
  systemctl enable --now gpsd
  echo "    GPS nalezeno na $GPS_DEV"
else
  echo "    GPS modul nenalezen – připojte ho a spusťte: sudo dpkg-reconfigure gpsd"
fi

echo "==> Bluetooth"
systemctl enable --now bluetooth

echo "==> Služby systemd"
cp "$APP_DIR/systemd/"*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now chasing-tail.service chasing-tail-web.service

IP=$(hostname -I | awk '{print $1}')
echo
echo "Hotovo. Dashboard: http://$IP:5000"
echo "Stav:  systemctl status chasing-tail   |   Log: journalctl -u chasing-tail -f"
