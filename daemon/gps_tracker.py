"""GPS tracker — čte polohu z UART modulu nebo gpsd daemona.

Podporované módy (config.yaml -> gps.device):
  - '/dev/ttyUSB0'  – přímé čtení NMEA vět přes pyserial
  - 'gpsd'          – připojení k lokálnímu gpsd (port 2947)

Doporučený GPS modul pro RPi: Beitian BN-880 nebo u-blox NEO-M8N.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)


class GPSTracker:
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._lat: float | None = None
        self._lon: float | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if not self._cfg.get("enabled", True):
            logger.info("GPS je vypnuto v konfiguraci")
            return
        self._stop.clear()
        device = self._cfg.get("device", "gpsd")
        target = self._read_gpsd if device == "gpsd" else self._read_uart
        self._thread = threading.Thread(target=target,
                                        name="gps-tracker", daemon=True)
        self._thread.start()
        logger.info("GPS tracker spuštěn (device=%s)", device)

    def stop(self):
        self._stop.set()

    def get_location(self) -> tuple[float, float] | None:
        with self._lock:
            if self._lat is not None and self._lon is not None:
                return (self._lat, self._lon)
            return None

    def _set_location(self, lat: float, lon: float):
        with self._lock:
            self._lat = lat
            self._lon = lon

    def _read_gpsd(self):
        try:
            import gpsd
        except ImportError:
            logger.error("gpsd-py3 není nainstalováno")
            return
        while not self._stop.is_set():
            try:
                gpsd.connect()
                while not self._stop.is_set():
                    packet = gpsd.get_current()
                    if packet.mode >= 2:
                        self._set_location(packet.lat, packet.lon)
                    time.sleep(1)
            except Exception as exc:
                logger.warning("gpsd error: %s — zkouším znovu za 5 s", exc)
                time.sleep(5)

    def _read_uart(self):
        try:
            import serial
        except ImportError:
            logger.error("pyserial není nainstalováno")
            return
        device = self._cfg.get("device", "/dev/ttyUSB0")
        baud   = self._cfg.get("baud", 9600)
        while not self._stop.is_set():
            try:
                with serial.Serial(device, baud, timeout=1) as ser:
                    while not self._stop.is_set():
                        line = ser.readline().decode("ascii", errors="ignore").strip()
                        loc = _parse_gprmc(line) or _parse_gpgga(line)
                        if loc:
                            self._set_location(*loc)
            except Exception as exc:
                logger.warning("UART GPS error: %s — zkouším znovu za 5 s", exc)
                time.sleep(5)


def _parse_gprmc(sentence: str) -> tuple[float, float] | None:
    """Parsuje $GPRMC větu, vrátí (lat, lon) nebo None."""
    if not sentence.startswith("$GPRMC"):
        return None
    parts = sentence.split(",")
    if len(parts) < 7 or parts[2] != "A":
        return None
    try:
        lat = _nmea_to_decimal(parts[3], parts[4])
        lon = _nmea_to_decimal(parts[5], parts[6])
        return lat, lon
    except Exception:
        return None


def _parse_gpgga(sentence: str) -> tuple[float, float] | None:
    """Parsuje $GPGGA větu, vrátí (lat, lon) nebo None."""
    if not sentence.startswith("$GPGGA"):
        return None
    parts = sentence.split(",")
    if len(parts) < 6 or parts[6] == "0":
        return None
    try:
        lat = _nmea_to_decimal(parts[2], parts[3])
        lon = _nmea_to_decimal(parts[4], parts[5])
        return lat, lon
    except Exception:
        return None


def _nmea_to_decimal(value: str, direction: str) -> float:
    """Převede NMEA souřadnici (DDmm.mmmm) na desetinné stupně."""
    if len(value) < 4:
        raise ValueError(f"Krátká hodnota: {value!r}")
    dot = value.index(".")
    degrees = float(value[: dot - 2])
    minutes = float(value[dot - 2:])
    decimal = degrees + minutes / 60.0
    if direction in ("S", "W"):
        decimal = -decimal
    return decimal
