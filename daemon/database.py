"""SQLite databáze pro záznamy o zařízeních, clustery a upozornění."""
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path


_CREATE_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sightings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mac         TEXT    NOT NULL,
    source      TEXT    NOT NULL DEFAULT 'wifi',  -- wifi | bt
    rssi        INTEGER,
    lat         REAL,
    lon         REAL,
    ts          REAL    NOT NULL                   -- unix timestamp
);
CREATE INDEX IF NOT EXISTS idx_sightings_mac ON sightings(mac);
CREATE INDEX IF NOT EXISTS idx_sightings_ts  ON sightings(ts);

CREATE TABLE IF NOT EXISTS devices (
    mac          TEXT PRIMARY KEY,
    source       TEXT NOT NULL DEFAULT 'wifi',
    manufacturer TEXT,
    first_seen   REAL NOT NULL,
    last_seen    REAL NOT NULL,
    sighting_count INTEGER NOT NULL DEFAULT 0,
    cluster_id   INTEGER,
    score        REAL    NOT NULL DEFAULT 0.0,
    alerted      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS clusters (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   REAL    NOT NULL,
    updated_at   REAL    NOT NULL,
    device_count INTEGER NOT NULL DEFAULT 0,
    score        REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER REFERENCES clusters(id),
    mac        TEXT,                               -- NULL = celý cluster
    score      REAL    NOT NULL,
    message    TEXT    NOT NULL,
    ts         REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS ignored (
    mac      TEXT PRIMARY KEY,
    label    TEXT,
    source   TEXT NOT NULL DEFAULT 'manual',       -- manual | baseline
    added_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _tx(self):
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self):
        with self._tx() as c:
            c.executescript(_CREATE_SQL)

    # ------------------------------------------------------------------ writes

    def log_sighting(self, mac: str, source: str = "wifi",
                     rssi: int | None = None,
                     lat: float | None = None,
                     lon: float | None = None,
                     ts: float | None = None):
        ts = ts or time.time()
        with self._tx() as c:
            c.execute(
                "INSERT INTO sightings(mac, source, rssi, lat, lon, ts) "
                "VALUES (?,?,?,?,?,?)",
                (mac.upper(), source, rssi, lat, lon, ts)
            )
            c.execute(
                """INSERT INTO devices(mac, source, first_seen, last_seen, sighting_count)
                   VALUES (?,?,?,?,1)
                   ON CONFLICT(mac) DO UPDATE SET
                     last_seen=excluded.last_seen,
                     sighting_count=sighting_count+1,
                     source=excluded.source""",
                (mac.upper(), source, ts, ts)
            )

    def update_device(self, mac: str, manufacturer: str | None = None,
                      cluster_id: int | None = None, score: float | None = None,
                      alerted: bool | None = None):
        fields, vals = [], []
        if manufacturer is not None:
            fields.append("manufacturer=?"); vals.append(manufacturer)
        if cluster_id is not None:
            fields.append("cluster_id=?"); vals.append(cluster_id)
        if score is not None:
            fields.append("score=?"); vals.append(score)
        if alerted is not None:
            fields.append("alerted=?"); vals.append(int(alerted))
        if not fields:
            return
        vals.append(mac.upper())
        with self._tx() as c:
            c.execute(f"UPDATE devices SET {', '.join(fields)} WHERE mac=?", vals)

    def upsert_cluster(self, cluster_id: int | None, device_count: int,
                       score: float) -> int:
        now = time.time()
        with self._tx() as c:
            if cluster_id is None:
                cur = c.execute(
                    "INSERT INTO clusters(created_at, updated_at, device_count, score) "
                    "VALUES (?,?,?,?)", (now, now, device_count, score)
                )
                return cur.lastrowid
            else:
                c.execute(
                    "UPDATE clusters SET updated_at=?, device_count=?, score=? WHERE id=?",
                    (now, device_count, score, cluster_id)
                )
                return cluster_id

    def log_alert(self, message: str, score: float,
                  cluster_id: int | None = None, mac: str | None = None):
        with self._tx() as c:
            c.execute(
                "INSERT INTO alerts(cluster_id, mac, score, message, ts) VALUES (?,?,?,?,?)",
                (cluster_id, mac.upper() if mac else None, score, message, time.time())
            )

    def add_ignored(self, macs, label: str | None = None, source: str = "manual") -> int:
        """Přidá MAC adresy na seznam ignorovaných. Vrátí počet nově přidaných."""
        now = time.time()
        with self._tx() as c:
            before = c.total_changes
            c.executemany(
                "INSERT OR IGNORE INTO ignored(mac, label, source, added_at) VALUES (?,?,?,?)",
                [(m.upper(), label, source, now) for m in macs],
            )
            return c.total_changes - before

    def remove_ignored(self, mac: str) -> int:
        with self._tx() as c:
            return c.execute("DELETE FROM ignored WHERE mac=?", (mac.upper(),)).rowcount

    def clear_ignored(self, source: str) -> int:
        with self._tx() as c:
            return c.execute("DELETE FROM ignored WHERE source=?", (source,)).rowcount

    def purge_older_than(self, days: float) -> int:
        """Smaže záznamy a zařízení starší než `days` dní. Vrátí počet smazaných záznamů."""
        cutoff = time.time() - days * 86400
        with self._tx() as c:
            n = c.execute("DELETE FROM sightings WHERE ts<?", (cutoff,)).rowcount
            c.execute("DELETE FROM devices WHERE last_seen<?", (cutoff,))
            c.execute("DELETE FROM alerts WHERE ts<?", (cutoff,))
            c.execute("DELETE FROM clusters WHERE updated_at<? AND id NOT IN "
                      "(SELECT DISTINCT cluster_id FROM devices WHERE cluster_id IS NOT NULL)",
                      (cutoff,))
        return n

    # ------------------------------------------------------------------ reads

    def get_sightings_since(self, since: float,
                            mac: str | None = None) -> list[sqlite3.Row]:
        conn = self._conn()
        if mac:
            return conn.execute(
                "SELECT * FROM sightings WHERE ts>=? AND mac=? ORDER BY ts",
                (since, mac.upper())
            ).fetchall()
        return conn.execute(
            "SELECT * FROM sightings WHERE ts>=? ORDER BY ts", (since,)
        ).fetchall()

    def get_ignored(self) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT * FROM ignored ORDER BY added_at DESC, mac"
        ).fetchall()

    def get_ignored_macs(self) -> set[str]:
        return {r[0] for r in self._conn().execute("SELECT mac FROM ignored")}

    def get_macs_seen_since(self, since: float) -> set[str]:
        return {r[0] for r in self._conn().execute(
            "SELECT DISTINCT mac FROM sightings WHERE ts>=?", (since,))}

    def get_all_devices(self) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT * FROM devices ORDER BY last_seen DESC"
        ).fetchall()

    def get_device(self, mac: str) -> sqlite3.Row | None:
        return self._conn().execute(
            "SELECT * FROM devices WHERE mac=?", (mac.upper(),)
        ).fetchone()

    def get_clusters(self) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT * FROM clusters ORDER BY score DESC"
        ).fetchall()

    def get_devices_in_cluster(self, cluster_id: int) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT * FROM devices WHERE cluster_id=?", (cluster_id,)
        ).fetchall()

    def get_alerts(self, limit: int = 100) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()

    def get_last_alert_ts(self, cluster_id: int | None = None,
                          mac: str | None = None) -> float | None:
        conn = self._conn()
        if cluster_id is not None:
            row = conn.execute(
                "SELECT MAX(ts) FROM alerts WHERE cluster_id=?", (cluster_id,)
            ).fetchone()
        elif mac:
            row = conn.execute(
                "SELECT MAX(ts) FROM alerts WHERE mac=?", (mac.upper(),)
            ).fetchone()
        else:
            return None
        return row[0]

    def get_recent_locations(self, since: float) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT lat, lon, ts FROM sightings "
            "WHERE ts>=? AND lat IS NOT NULL AND lon IS NOT NULL "
            "ORDER BY ts DESC LIMIT 500",
            (since,)
        ).fetchall()

    def stats(self) -> dict:
        conn = self._conn()
        total_devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        total_alerts  = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        suspicious    = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE score>=0.55"
        ).fetchone()[0]
        clusters      = conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0]
        return {
            "total_devices": total_devices,
            "suspicious_devices": suspicious,
            "total_alerts": total_alerts,
            "clusters": clusters,
        }
