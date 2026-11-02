"""Hlavní daemon: spustí GPS, Wi-Fi a BT skenery a pravidelně analyzuje.

Spuštění:  sudo python -m daemon.main [--config config.yaml]
"""
import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from .analyzer import Analyzer
from .bt_scanner import BluetoothScanner
from .config import load_config
from .database import Database
from .gps_tracker import GPSTracker
from .notifier import Notifier
from .wifi_scanner import WiFiScanner


def setup_logging(cfg: dict):
    handlers = [logging.StreamHandler(sys.stdout)]
    log_file = cfg.get("file")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, cfg.get("level", "INFO")),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="Chasing Your Tail daemon")
    ap.add_argument("--config", help="cesta ke config.yaml")
    ap.add_argument("--no-wifi", action="store_true")
    ap.add_argument("--no-bt", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(cfg.get("logging", {}))
    log = logging.getLogger("chasing-tail")

    db = Database(cfg["database"]["path"])
    gps = GPSTracker(cfg.get("gps", {}))
    analyzer = Analyzer(db, cfg.get("analysis", {}))
    notifier = Notifier(db, cfg.get("alerts", {}))

    components = [gps]
    if not args.no_wifi:
        components.append(WiFiScanner(cfg["wifi"]["interface"], db, gps, cfg["wifi"]))
    if not args.no_bt:
        components.append(BluetoothScanner(db, gps, cfg.get("bluetooth", {})))

    stop = threading.Event()

    def shutdown(*_):
        log.info("Ukončuji…")
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for c in components:
        c.start()

    interval = cfg.get("analysis", {}).get("interval_seconds", 60)
    retention = cfg["database"].get("retention_days", 14)
    log.info("Daemon běží, analýza každých %d s", interval)
    runs = 0
    while not stop.wait(interval):
        try:
            notifier.process(analyzer.run())
            if runs % 60 == 0:
                n = db.purge_older_than(retention)
                if n:
                    log.info("Smazáno %d záznamů starších než %d dní", n, retention)
        except Exception:
            log.exception("Chyba analýzy")
        runs += 1

    for c in components:
        c.stop()


if __name__ == "__main__":
    main()
