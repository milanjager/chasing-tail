"""WiGLE.net integration — obohacuje MAC adresy o data z globální databáze sítí.

Konfigurace (config.yaml nebo config.local.yaml):
  wigle:
    api_name:  "AIDxxxxxx"      # WiGLE API name (z profilu na wigle.net)
    api_token: "xxxxxxxx"       # WiGLE API token
    enabled:   true

Bez přihlašovacích údajů (nebo enabled: false) vrací simulovaná data.
Simulovaná data jsou realistická a odpovídají demo scénáři (Praha).
"""
import base64
import hashlib
import logging
import time

import requests

logger = logging.getLogger(__name__)

WIGLE_WIFI_URL = "https://api.wigle.net/api/v2/network/search"
WIGLE_BT_URL   = "https://api.wigle.net/api/v2/bluetooth/search"

# OUI prefix → výrobce (zkrácená tabulka pro demo)
_OUI = {
    "3C:22:FB": "Samsung Electronics",
    "F4:5C:89": "Garmin International",
    "72:DE:AD": "Xiaomi Communications",
    "D2:4E:7A": "Apple (AirTag/Find My)",
    "E6:11:22": "u-blox AG",
    "00:1A:2B": "Cisco Systems",
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Trading",
    "8A:1F:3E": "Apple (iPhone)",
    "C8:3A:35": "Apple (Apple Watch)",
    "AA:BB:CC": "OnePlus Technology",
    "DD:EE:FF": "Huawei Technologies",
    "11:22:33": "Google (Pixel)",
}

# Simulovaná poloha: kde byl daný MAC v databázi WiGLE naposledy viděn
_SIM_LOCATIONS = {
    "3C:22:FB:11:22:33": (50.0813, 14.4280, "Václavské náměstí, Praha"),
    "F4:5C:89:AA:BB:CC": (50.0813, 14.4280, "Václavské náměstí, Praha"),
    "72:DE:AD:BE:EF:01": (50.0870, 14.4208, "Staroměstské náměstí, Praha"),
    "D2:4E:7A:01:02:03": (50.0875, 14.4280, "Prašná brána, Praha"),
    "E6:11:22:33:44:55": (50.0810, 14.4135, "Národní divadlo, Praha"),
    "AA:BB:CC:11:22:33": (50.0880, 14.4040, "Malostranské náměstí, Praha"),
    "DD:EE:FF:44:55:66": (50.0905, 14.4005, "Pražský hrad"),
    "11:22:33:AA:BB:CC": (50.0833, 14.4030, "Petřín, Praha"),
}

# Simulovaná jména BT zařízení
_SIM_BT_NAMES = {
    "3C:22:FB:11:22:33": "Galaxy S24",
    "F4:5C:89:AA:BB:CC": "Garmin Forerunner 965",
    "72:DE:AD:BE:EF:01": "Redmi Note 13",
    "D2:4E:7A:01:02:03": "AirTag",
    "E6:11:22:33:44:55": "GT06N Tracker",
    "C8:3A:35:10:20:30": "Apple Watch Series 9",
    "8A:1F:3E:44:55:66": "iPhone 16",
    "AA:BB:CC:11:22:33": "OnePlus 12",
    "DD:EE:FF:44:55:66": "Huawei Mate 60",
    "11:22:33:AA:BB:CC": "Pixel 9",
}

# Simulovaná SSID pro WiFi probe requesty
_SIM_SSIDS = {
    "3C:22:FB:11:22:33": ["AndroidShare_5G", "HOME-WIFI-5G", "T-Mobile_Auto"],
    "72:DE:AD:BE:EF:01": ["Xiaomi_Home", "Vodafone-7A3B"],
    "AA:BB:CC:11:22:33": ["OnePlus_Network", "O2-Wifi-Home"],
    "DD:EE:FF:44:55:66": ["HuaweiP60_AP", "FRITZ!Box 7590"],
    "11:22:33:AA:BB:CC": ["GooglePixel_Hotspot", "O2-Home-5G"],
}


def _oui_manufacturer(mac: str) -> str:
    prefix = mac.upper()[:8]
    return _OUI.get(prefix, "Neznámý výrobce")


def _sim_sightings(mac: str) -> int:
    """Deterministický počet výskytů v WiGLE databázi z MAC."""
    h = int(hashlib.md5(mac.encode()).hexdigest()[:4], 16)
    return 50 + (h % 2000)


def _sim_first_seen(mac: str) -> str:
    h = int(hashlib.md5(mac.encode()).hexdigest()[4:8], 16)
    days_ago = 30 + (h % 700)
    ts = time.time() - days_ago * 86400
    return time.strftime("%Y%m%d", time.localtime(ts))


def _simulate(mac: str, source: str) -> dict:
    mac = mac.upper()
    loc = _SIM_LOCATIONS.get(mac)
    result = {
        "mac":          mac,
        "manufacturer": _oui_manufacturer(mac),
        "source":       "wigle-sim",
        "db_sightings": _sim_sightings(mac),
        "first_seen":   _sim_first_seen(mac),
        "simulated":    True,
    }
    if loc:
        result["lat"]     = loc[0]
        result["lon"]     = loc[1]
        result["location_label"] = loc[2]
    if source == "bt" or mac in _SIM_BT_NAMES:
        result["bt_name"] = _SIM_BT_NAMES.get(mac, "")
    if source == "wifi" and mac in _SIM_SSIDS:
        result["ssids"] = _SIM_SSIDS[mac]
    return result


class WigleClient:
    def __init__(self, cfg: dict):
        wcfg = cfg.get("wigle", {})
        self._enabled   = wcfg.get("enabled", True)
        self._api_name  = wcfg.get("api_name", "")
        self._api_token = wcfg.get("api_token", "")
        self._real = bool(self._api_name and self._api_token)
        if self._real:
            cred = base64.b64encode(
                f"{self._api_name}:{self._api_token}".encode()
            ).decode()
            self._headers = {"Authorization": f"Basic {cred}"}
        else:
            self._headers = {}

    @property
    def simulated(self) -> bool:
        return not self._real

    def lookup(self, mac: str, source: str = "wifi") -> dict | None:
        """Vrátí obohacená data o MAC adrese z WiGLE, nebo None při chybě."""
        if not self._enabled:
            return None
        if not self._real:
            return _simulate(mac, source)
        return self._real_lookup(mac, source)

    def _real_lookup(self, mac: str, source: str) -> dict | None:
        url = WIGLE_BT_URL if source == "bt" else WIGLE_WIFI_URL
        try:
            r = requests.get(url, params={"netid": mac}, headers=self._headers, timeout=8)
            if r.status_code == 401:
                logger.error("WiGLE: neplatné přihlašovací údaje")
                return None
            if r.status_code == 429:
                logger.warning("WiGLE: rate limit, zkuste za chvíli")
                return None
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("WiGLE lookup %s selhal: %s", mac, exc)
            return None

        results = data.get("results", [])
        if not results:
            return {"mac": mac.upper(), "manufacturer": _oui_manufacturer(mac),
                    "source": "wigle-real", "db_sightings": 0, "simulated": False}

        hit = results[0]
        out = {
            "mac":          mac.upper(),
            "manufacturer": hit.get("manufacturer") or _oui_manufacturer(mac),
            "source":       "wigle-real",
            "db_sightings": data.get("totalResults", len(results)),
            "first_seen":   hit.get("firsttime", ""),
            "last_seen_db": hit.get("lasttime", ""),
            "simulated":    False,
        }
        if hit.get("trilat") and hit.get("trilong"):
            out["lat"] = hit["trilat"]
            out["lon"] = hit["trilong"]
        if source == "wifi":
            out["ssid"]       = hit.get("ssid", "")
            out["encryption"] = hit.get("encryption", "")
            out["channel"]    = hit.get("channel")
        if source == "bt":
            out["bt_name"] = hit.get("ssid", "")
        return out
