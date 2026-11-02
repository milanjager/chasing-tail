"""Upozornění na podezřelé osoby (cluster nebo samostatné zařízení).

Kanály: log soubor, notify-send (desktop), ntfy.sh, Pushbullet.
Pro každou osobu se upozorní nejvýš jednou za cooldown_minutes.
"""
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, db, cfg: dict):
        self._db = db
        self._cfg = cfg
        self._cooldown = cfg.get("cooldown_minutes", 30) * 60
        self._alert_log = None
        log_file = cfg.get("log_file")
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            self._alert_log = logging.getLogger("chasing-tail.alerts")
            if not self._alert_log.handlers:
                h = logging.FileHandler(log_file, encoding="utf-8")
                h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                self._alert_log.addHandler(h)
                self._alert_log.setLevel(logging.INFO)

    def process(self, persons: list[dict]) -> list[str]:
        """Odešle upozornění pro všechny podezřelé osoby. Vrátí odeslané zprávy."""
        if not self._cfg.get("enabled", True):
            return []
        sent = []
        for p in persons:
            if p["suspicious"]:
                msg = self._notify(p)
                if msg:
                    sent.append(msg)
        return sent

    def _notify(self, person: dict) -> str | None:
        cid = person["cluster_id"]
        macs = person["macs"]
        if cid:
            last = self._db.get_last_alert_ts(cluster_id=cid)
        else:
            last = self._db.get_last_alert_ts(mac=macs[0])
        if last and time.time() - last < self._cooldown:
            return None

        if cid:
            msg = (f"Podezřelá osoba #{cid}: {len(macs)} zařízení "
                   f"({', '.join(macs[:4])}{' …' if len(macs) > 4 else ''}), "
                   f"skóre {person['score']:.2f}")
            self._db.log_alert(msg, person["score"], cluster_id=cid)
        else:
            msg = f"Podezřelé zařízení {macs[0]}, skóre {person['score']:.2f}"
            self._db.log_alert(msg, person["score"], mac=macs[0])

        if self._alert_log:
            self._alert_log.info(msg)
        logger.warning(msg)
        self._send_desktop(msg)
        self._send_ntfy(msg)
        self._send_pushbullet(msg)
        return msg

    def _send_desktop(self, msg: str):
        try:
            subprocess.run(["notify-send", "-u", "critical", "Chasing Your Tail", msg],
                           timeout=3, capture_output=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    def _send_ntfy(self, msg: str):
        topic = self._cfg.get("ntfy_topic", "")
        if not topic:
            return
        try:
            import requests
            requests.post(f"https://ntfy.sh/{topic}", data=msg.encode("utf-8"),
                          headers={"Title": "Chasing Your Tail", "Priority": "high"},
                          timeout=5)
        except Exception as exc:
            logger.warning("ntfy selhalo: %s", exc)

    def _send_pushbullet(self, msg: str):
        token = self._cfg.get("pushbullet_token", "")
        if not token:
            return
        try:
            import requests
            requests.post("https://api.pushbullet.com/v2/pushes",
                          headers={"Access-Token": token},
                          json={"type": "note", "title": "Chasing Your Tail", "body": msg},
                          timeout=5)
        except Exception as exc:
            logger.warning("Pushbullet selhalo: %s", exc)
