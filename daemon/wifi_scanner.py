"""Wi-Fi scanner — sbírá 802.11 probe requesty v monitor mode.

Vyžaduje:
  - root práva
  - Wi-Fi adaptér s podporou monitor mode (např. ALFA AWUS036ACH)
  - scapy: pip install scapy

Nastavení monitor mode před spuštěním:
  sudo ip link set wlan1 down
  sudo iw dev wlan1 set type monitor
  sudo ip link set wlan1 up

Nebo automaticky přes install.sh.
"""
import logging
import threading
import time
from queue import Queue

logger = logging.getLogger(__name__)


class WiFiScanner:
    """Pasivní sniffer probe requestů na zadaném rozhraní."""

    def __init__(self, interface: str, db, gps, cfg: dict):
        self._iface = interface
        self._db = db
        self._gps = gps
        self._cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hop_thread: threading.Thread | None = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._scan_loop,
                                        name="wifi-scanner", daemon=True)
        self._thread.start()
        if self._cfg.get("channel_hop", True):
            self._hop_thread = threading.Thread(target=self._hop_loop,
                                                name="wifi-hopper", daemon=True)
            self._hop_thread.start()
        logger.info("Wi-Fi scanner spuštěn na rozhraní %s", self._iface)

    def stop(self):
        self._stop.set()

    def _scan_loop(self):
        try:
            from scapy.all import sniff, Dot11ProbeReq, Dot11
        except ImportError:
            logger.error("scapy není nainstalováno — Wi-Fi scanner nefunkční")
            return

        def handler(pkt):
            if self._stop.is_set():
                return
            if pkt.haslayer(Dot11ProbeReq):
                mac = pkt[Dot11].addr2
                if mac is None or mac == "ff:ff:ff:ff:ff:ff":
                    return
                rssi = pkt.dBm_AntSignal if hasattr(pkt, "dBm_AntSignal") else None
                loc = self._gps.get_location() if self._gps else None
                lat, lon = (loc if loc else (None, None))
                self._db.log_sighting(mac, source="wifi", rssi=rssi,
                                       lat=lat, lon=lon)

        sniff(iface=self._iface, prn=handler,
              stop_filter=lambda _: self._stop.is_set(),
              store=False)

    def _hop_loop(self):
        """Přepíná kanály 1–13 každých hop_interval sekund."""
        import subprocess
        interval = self._cfg.get("hop_interval", 0.5)
        channels = list(range(1, 14))
        idx = 0
        while not self._stop.is_set():
            ch = channels[idx % len(channels)]
            try:
                subprocess.run(
                    ["iwconfig", self._iface, "channel", str(ch)],
                    capture_output=True, timeout=1
                )
            except Exception:
                pass
            idx += 1
            time.sleep(interval)
