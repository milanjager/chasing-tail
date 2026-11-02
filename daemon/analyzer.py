"""Analyzátor podezřelých zařízení a seskupování do „osob“ (clustering).

Skóre podezřelosti (0–1):
  time_ratio     = podíl časových oken, ve kterých bylo zařízení vidět
  location_ratio = podíl vašich různých míst (GPS buňky ~100 m), kde bylo vidět
  score = 0.4 * time_ratio + 0.6 * location_ratio   (pokud máte ≥ 2 místa)
  score = time_ratio                                 (bez pohybu / bez GPS)

Clustering (telefon + hodinky = jedna osoba):
  Dvě zařízení se spojí, pokud sdílejí ≥ min_shared_buckets oken a zároveň
    - korelace přítomnosti (phi) ≥ min_phi: objevují se A mizí spolu, nebo
    - Jaccard ≥ min_jaccard: obě jsou vidět téměř pořád (phi tu nejde spočítat).
  Phi odliší zařízení, které je jen často poblíž, od zařízení, které se pohybuje
  s jiným. Spojení je tranzitivní.
"""
import logging
import math
import time
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

DEFAULTS = {
    "window_hours": 2,
    "suspicion_threshold": 0.55,
    "min_sightings": 3,
    "time_bucket_minutes": 2,
    "min_shared_buckets": 5,
    "min_phi": 0.50,
    "min_jaccard": 0.90,
    "location_precision": 3,   # desetinná místa lat/lon → buňka ~100 m
    "ignore_macs": [],
}


def location_cell(lat, lon, precision: int):
    if lat is None or lon is None:
        return None
    return (round(lat, precision), round(lon, precision))


def jaccard(a: set, b: set) -> float:
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def phi(a: set, b: set, total: int) -> float:
    """Pearsonova korelace dvou binárních řad přítomnosti přes `total` oken."""
    n11, na, nb = len(a & b), len(a), len(b)
    denom = math.sqrt(na * (total - na) * nb * (total - nb))
    return (total * n11 - na * nb) / denom if denom else 0.0


def same_person(a: set, b: set, total: int, min_shared: int,
                min_phi: float, min_jaccard: float) -> bool:
    if len(a & b) < min_shared:
        return False
    return phi(a, b, total) >= min_phi or jaccard(a, b) >= min_jaccard


def cluster_devices(mac_buckets: dict[str, set[int]], total: int, min_shared: int,
                    min_phi: float, min_jaccard: float) -> list[set[str]]:
    """Union-Find; `total` = počet oken v analyzovaném období.
    Vrací jen skupiny s ≥ 2 zařízeními."""
    macs = sorted(mac_buckets)
    parent = {m: m for m in macs}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(macs):
        for b in macs[i + 1:]:
            if same_person(mac_buckets[a], mac_buckets[b], total,
                           min_shared, min_phi, min_jaccard):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

    groups: dict[str, set[str]] = defaultdict(set)
    for m in macs:
        groups[find(m)].add(m)
    return [g for g in groups.values() if len(g) >= 2]


def score_devices(sightings, cfg: dict) -> tuple[dict[str, dict], int]:
    """Čistá funkce: ze seznamu záznamů spočítá metriky pro každé zařízení.
    Vrací (zařízení, počet časových oken v období)."""
    bucket_s = cfg["time_bucket_minutes"] * 60
    prec = cfg["location_precision"]
    ignore = {m.upper() for m in cfg.get("ignore_macs", [])}

    buckets: dict[str, set[int]] = defaultdict(set)
    cells: dict[str, set] = defaultdict(set)
    counts: Counter = Counter()
    sources: dict[str, str] = {}
    all_buckets: set[int] = set()
    all_cells: set = set()

    for r in sightings:
        mac = r["mac"].upper()
        b = int(r["ts"] // bucket_s)
        all_buckets.add(b)
        cell = location_cell(r["lat"], r["lon"], prec)
        if cell:
            all_cells.add(cell)
        if mac in ignore:
            continue
        buckets[mac].add(b)
        counts[mac] += 1
        sources[mac] = r["source"]
        if cell:
            cells[mac].add(cell)

    span = (max(all_buckets) - min(all_buckets) + 1) if all_buckets else 1
    moving = len(all_cells) >= 2

    result = {}
    for mac, bks in buckets.items():
        if counts[mac] < cfg["min_sightings"]:
            continue
        time_ratio = len(bks) / span
        if moving:
            loc_ratio = len(cells[mac]) / len(all_cells)
            score = 0.4 * time_ratio + 0.6 * loc_ratio
        else:
            loc_ratio = None
            score = time_ratio
        result[mac] = {
            "mac": mac,
            "source": sources[mac],
            "buckets": bks,
            "sightings": counts[mac],
            "locations": len(cells[mac]),
            "time_ratio": round(time_ratio, 3),
            "location_ratio": None if loc_ratio is None else round(loc_ratio, 3),
            "score": round(min(score, 1.0), 3),
        }
    return result, span


class Analyzer:
    def __init__(self, db, cfg: dict | None = None):
        self._db = db
        self.cfg = {**DEFAULTS, **(cfg or {})}

    def run(self, now: float | None = None) -> list[dict]:
        """Analyzuje okno, zapíše skóre a clustery do DB.

        Vrací seznam „osob“ (cluster nebo samostatné zařízení), seřazený
        podle skóre: {cluster_id, macs, score, suspicious}.
        """
        now = now or time.time()
        since = now - self.cfg["window_hours"] * 3600
        cfg = {**self.cfg,
               "ignore_macs": [*self.cfg["ignore_macs"], *self._db.get_ignored_macs()]}
        devices, span = score_devices(self._db.get_sightings_since(since), cfg)

        groups = cluster_devices(
            {m: d["buckets"] for m, d in devices.items()}, span,
            self.cfg["min_shared_buckets"], self.cfg["min_phi"], self.cfg["min_jaccard"],
        )
        grouped = set().union(*groups) if groups else set()

        persons = []
        for members in groups:
            score = max(devices[m]["score"] for m in members)
            cluster_id = self._db.upsert_cluster(
                self._reuse_cluster_id(members), len(members), score)
            for m in members:
                self._db.update_device(m, cluster_id=cluster_id, score=devices[m]["score"])
            persons.append({"cluster_id": cluster_id, "macs": sorted(members), "score": score})

        for mac, d in devices.items():
            if mac in grouped:
                continue
            self._db.update_device(mac, score=d["score"], cluster_id=0)
            persons.append({"cluster_id": None, "macs": [mac], "score": d["score"]})

        threshold = self.cfg["suspicion_threshold"]
        for p in persons:
            p["suspicious"] = p["score"] >= threshold
        persons.sort(key=lambda p: p["score"], reverse=True)

        logger.info("Analýza: %d zařízení, %d skupin, %d podezřelých osob",
                    len(devices), len(groups), sum(p["suspicious"] for p in persons))
        return persons

    def _reuse_cluster_id(self, members: set[str]) -> int | None:
        """Ponechá ID clusteru z minulé analýzy, aby se neupozorňovalo znovu."""
        ids = Counter()
        for m in members:
            row = self._db.get_device(m)
            if row and row["cluster_id"]:
                ids[row["cluster_id"]] += 1
        return ids.most_common(1)[0][0] if ids else None
