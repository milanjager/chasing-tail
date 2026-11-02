"""Bluetooth / BLE scanner pomocí bleak.

Skenuje okolní BLE zařízení a loguje jejich MAC adresy.
Vyžaduje: pip install bleak  a  bluetoothd běžící na RPi.

Pozn.: BLE zařízení mají od Androidu 10+ / iOS 14+ randomizované MAC.
       Tato data jsou tedy méně spolehlivá než Wi-Fi probe requesty.
"""
import asyncio
import logging
import threading
import time

logger = logging.getLogger(__name__)


class BluetoothScanner:
    def __init__(self, db, gps, cfg: dict):
        self._db = db
        self._gps = gps
        self._cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if not self._cfg.get("enabled", True):
            logger.info("Bluetooth scanner je vypnut v konfiguraci")
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_async_loop,
                                        name="bt-scanner", daemon=True)
        self._thread.start()
        logger.info("Bluetooth scanner spuštěn")

    def stop(self):
        self._stop.set()

    def _run_async_loop(self):
        try:
            asyncio.run(self._scan_loop())
        except Exception as exc:
            logger.error("Bluetooth scanner selhal: %s", exc)

    async def _scan_loop(self):
        try:
            from bleak import BleakScanner
        except ImportError:
            logger.error("bleak není nainstalováno — BT scanner nefunkční")
            return

        duration = self._cfg.get("scan_duration", 5)
        interval = self._cfg.get("scan_interval", 10)

        while not self._stop.is_set():
            try:
                devices = await BleakScanner.discover(timeout=duration)
                loc = self._gps.get_location() if self._gps else None
                lat, lon = (loc if loc else (None, None))
                for dev in devices:
                    mac = dev.address
                    rssi = dev.rssi
                    self._db.log_sighting(mac, source="bt", rssi=rssi,
                                           lat=lat, lon=lon)
                logger.debug("BT scan: nalezeno %d zařízení", len(devices))
            except Exception as exc:
                logger.warning("BT scan error: %s", exc)

            await asyncio.sleep(interval)
