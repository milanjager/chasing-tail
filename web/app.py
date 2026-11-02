"""Webový dashboard (Flask). Spuštění: python -m web.app"""
import hmac
import re
import sys
import time
from collections import defaultdict

from flask import Flask, Response, jsonify, render_template, request

from daemon.config import load_config
from daemon.database import Database


MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def is_randomized(mac: str) -> bool:
    """Lokálně spravovaná (randomizovaná) MAC má nastavený bit 0x02 v 1. bajtu."""
    try:
        return bool(int(mac[:2], 16) & 0x02)
    except ValueError:
        return False


def create_app(db: Database, cfg: dict) -> Flask:
    app = Flask(__name__)
    threshold = cfg.get("analysis", {}).get("suspicion_threshold", 0.55)
    web = cfg.get("web", {})
    password = web.get("password", "")
    username = web.get("username", "admin")

    @app.before_request
    def require_auth():
        if not password:
            return None
        auth = request.authorization
        if (auth and hmac.compare_digest(auth.username or "", username)
                and hmac.compare_digest(auth.password or "", password)):
            return None
        return Response("Přihlaste se", 401,
                        {"WWW-Authenticate": 'Basic realm="Chasing Your Tail"'})

    @app.before_request
    def require_json_for_writes():
        # Formulář z cizí stránky neumí poslat JSON bez CORS → ochrana před CSRF.
        if request.method == "POST" and not request.is_json:
            return jsonify({"error": "očekávám JSON"}), 415
        return None

    def device_dict(row) -> dict:
        return {
            "mac": row["mac"],
            "source": row["source"],
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
            "sightings": row["sighting_count"],
            "score": row["score"],
            "cluster_id": row["cluster_id"] or None,
            "randomized": is_randomized(row["mac"]),
        }

    @app.get("/")
    def index():
        return render_template("index.html", threshold=threshold)

    @app.get("/api/stats")
    def stats():
        persons = _persons()
        return jsonify({
            "devices": len(db.get_all_devices()),
            "persons": len(persons),
            "groups": sum(1 for p in persons if p["cluster_id"]),
            "suspicious": sum(1 for p in persons if p["suspicious"]),
            "alerts": len(db.get_alerts(10000)),
            "ignored": len(db.get_ignored_macs()),
        })

    def _persons() -> list[dict]:
        groups: dict[int, list[dict]] = defaultdict(list)
        persons = []
        ignored = db.get_ignored_macs()
        for row in db.get_all_devices():
            if row["mac"] in ignored:
                continue
            d = device_dict(row)
            if d["cluster_id"]:
                groups[d["cluster_id"]].append(d)
            else:
                persons.append({"cluster_id": None, "devices": [d]})
        for cid, devs in groups.items():
            persons.append({"cluster_id": cid, "devices": devs})
        for p in persons:
            p["score"] = max(d["score"] for d in p["devices"])
            p["last_seen"] = max(d["last_seen"] for d in p["devices"])
            p["sightings"] = sum(d["sightings"] for d in p["devices"])
            p["suspicious"] = p["score"] >= threshold
        persons.sort(key=lambda p: (p["score"], p["last_seen"]), reverse=True)
        return persons

    @app.get("/api/persons")
    def persons():
        only = request.args.get("suspicious") == "1"
        ps = _persons()
        return jsonify([p for p in ps if p["suspicious"]] if only else ps)

    @app.get("/api/device/<mac>")
    def device(mac):
        since = time.time() - 24 * 3600
        rows = db.get_sightings_since(since, mac=mac)
        return jsonify([
            {"ts": r["ts"], "rssi": r["rssi"], "lat": r["lat"], "lon": r["lon"],
             "source": r["source"]} for r in rows
        ])

    # ---------------------------------------------------- ignorovaná zařízení

    @app.get("/api/ignored")
    def ignored_list():
        return jsonify([dict(r) for r in db.get_ignored()])

    @app.post("/api/ignored")
    def ignored_add():
        body = request.get_json(silent=True) or {}
        raw = body.get("macs") if isinstance(body, dict) else None
        if not isinstance(raw, list):
            return jsonify({"error": "očekávám seznam macs"}), 400
        macs = [str(m).strip().upper().replace("-", ":") for m in raw]
        invalid = [m for m in macs if not MAC_RE.match(m)]
        if not macs or invalid:
            return jsonify({"error": "neplatná MAC adresa", "invalid": invalid}), 400
        label = str(body.get("label") or "").strip()[:60] or None
        return jsonify({"added": db.add_ignored(macs, label, "manual")})

    @app.delete("/api/ignored/<mac>")
    def ignored_remove(mac):
        return jsonify({"removed": db.remove_ignored(mac)})

    # ---------------------------------------------------- odrušení okolí

    def _minutes(value) -> float:
        try:
            return min(max(float(value), 1), 1440)
        except (TypeError, ValueError):
            return 5.0

    def _ambient(minutes: float) -> list[str]:
        seen = db.get_macs_seen_since(time.time() - minutes * 60)
        return sorted(seen - db.get_ignored_macs())

    @app.get("/api/ambient")
    def ambient():
        m = _minutes(request.args.get("minutes", 5))
        return jsonify({"minutes": m, "count": len(_ambient(m))})

    @app.post("/api/ambient/ignore")
    def ambient_ignore():
        m = _minutes((request.get_json(silent=True) or {}).get("minutes", 5))
        label = time.strftime("okolí %d. %m. %H:%M")
        return jsonify({"added": db.add_ignored(_ambient(m), label, "baseline")})

    @app.delete("/api/ambient")
    def ambient_clear():
        return jsonify({"removed": db.clear_ignored("baseline")})

    @app.get("/api/alerts")
    def alerts():
        return jsonify([dict(r) for r in db.get_alerts(100)])

    @app.get("/api/track")
    def track():
        hours = float(request.args.get("hours", 2))
        rows = db.get_recent_locations(time.time() - hours * 3600)
        seen, pts = set(), []
        for r in rows:
            key = (round(r["lat"], 5), round(r["lon"], 5))
            if key not in seen:
                seen.add(key)
                pts.append({"lat": r["lat"], "lon": r["lon"], "ts": r["ts"]})
        return jsonify(pts)

    return app


def main():
    cfg = load_config()
    db = Database(cfg["database"]["path"])
    web = cfg.get("web", {})
    host = web.get("host", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost") and not web.get("password"):
        sys.exit("Dashboard je dostupný ze sítě, nastavte web.password v config.local.yaml")
    create_app(db, cfg).run(host=host,
                            port=web.get("port", 5000),
                            debug=web.get("debug", False))


if __name__ == "__main__":
    main()
