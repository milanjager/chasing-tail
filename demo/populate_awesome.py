"""Rich demo data → /tmp/chasing-tail-dev.db

Scenario (3-hour walk through Prague):
  - You: phone + watch (ignored as home devices)
  - Stalker A: phone + watch, follow you everywhere (cluster, high score)
  - Stalker B: single phone, follows ~80 % of stops
  - Hidden AirTag: BT tracker seen at nearly every stop
  - Hidden car tracker: seen at 6/8 stops, BT
  - Café regular: seen only at stop 3, 40 min
  - Office neighbour: seen at stop 1 and home only (ignored after home calibration)
  - 200 random passers-by
  - 3 extra suspicious solo devices seen at 5+ stops
"""
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.analyzer import Analyzer
from daemon.database import Database
from daemon.notifier import Notifier

DB_PATH = "/tmp/chasing-tail-dev.db"

ROUTE = [
    (50.0870, 14.4208),  # Staroměstské náměstí
    (50.0865, 14.4114),  # Karlův most
    (50.0880, 14.4040),  # Malostranské náměstí
    (50.0905, 14.4005),  # Pražský hrad
    (50.0833, 14.4030),  # Petřín
    (50.0810, 14.4135),  # Národní divadlo
    (50.0813, 14.4280),  # Václavské náměstí
    (50.0875, 14.4280),  # Prašná brána
]
HOME = (50.0755, 14.4430)
MINUTES = 180
HOME_MINUTES = 15
PER_STOP = MINUTES / len(ROUTE)

MY_PHONE        = "8A:1F:3E:44:55:66"
MY_WATCH        = "C8:3A:35:10:20:30"
STALKER_A_PHONE = "3C:22:FB:11:22:33"
STALKER_A_WATCH = "F4:5C:89:AA:BB:CC"
STALKER_B_PHONE = "72:DE:AD:BE:EF:01"
AIRTAG          = "D2:4E:7A:01:02:03"
CAR_TRACKER     = "E6:11:22:33:44:55"
CAFE_REGULAR    = "00:1A:2B:3C:4D:5E"
OFFICE_NBR      = "B8:27:EB:FF:00:01"
SUSPICIOUS_1    = "AA:BB:CC:11:22:33"
SUSPICIOUS_2    = "DD:EE:FF:44:55:66"
SUSPICIOUS_3    = "11:22:33:AA:BB:CC"

HOME_DEVICES = [
    (MY_PHONE,   "wifi"),
    (MY_WATCH,   "bt"),
    ("B8:27:EB:AA:00:01", "wifi"),   # TV
    ("DC:A6:32:12:34:56", "wifi"),   # laptop
    (OFFICE_NBR, "bt"),
]


def rand_mac(rng):
    first = rng.randrange(0, 256) | 0x02
    return ":".join(f"{b:02X}" for b in [first & 0xFE] + [rng.randrange(256) for _ in range(5)])


def position(minute, rng):
    idx = min(int(minute // PER_STOP), len(ROUTE) - 1)
    lat, lon = ROUTE[idx]
    return idx, lat + rng.uniform(-0.0002, 0.0002), lon + rng.uniform(-0.0002, 0.0002)


def main():
    rng = random.Random(99)
    own = random.Random(1099)

    db = Database(DB_PATH)
    now = time.time()
    walk_start = now - MINUTES * 60
    home_start = walk_start - HOME_MINUTES * 60

    def log(mac, source, lat, lon, ts, rssi=None, r=None):
        r = r or rng
        db.log_sighting(mac, source=source,
                        rssi=rssi or r.randint(-85, -55),
                        lat=lat, lon=lon,
                        ts=ts + r.uniform(0, 55))

    # --- Home phase ---
    for m in range(HOME_MINUTES):
        ts = home_start + m * 60
        for mac, src in HOME_DEVICES:
            if own.random() < 0.9:
                log(mac, src, *HOME, ts, r=own)

    # --- Walk phase ---
    passers = [rand_mac(rng) for _ in range(200)]
    passer_slots = {mac: (rng.randrange(MINUTES), rng.randint(1, 4)) for mac in passers}
    cafe_start = int(PER_STOP * 2)   # Malostranské náměstí
    gap_a = 0

    # suspicious solo devices: seen at stops 0,2,4,6,7
    sus_stops = {
        SUSPICIOUS_1: {0, 2, 4, 6, 7},
        SUSPICIOUS_2: {1, 3, 5, 6, 7},
        SUSPICIOUS_3: {0, 1, 2, 3, 5, 6},
    }

    for minute in range(MINUTES):
        idx, lat, lon = position(minute, rng)
        ts = walk_start + minute * 60

        # passers
        for mac, (start, dur) in passer_slots.items():
            if start <= minute < start + dur:
                log(mac, rng.choice(["wifi", "bt"]), lat, lon, ts)

        # café regular: stop 2, 40 min
        if cafe_start <= minute < cafe_start + 40:
            log(CAFE_REGULAR, "wifi", lat, lon, ts, rssi=rng.randint(-68, -55))

        # Stalker A (phone + watch) — gap occasionally
        if gap_a > 0:
            gap_a -= 1
        elif minute >= 8 and rng.random() < 0.06:
            gap_a = rng.randint(2, 5)
        elif minute >= 8:
            if rng.random() < 0.88:
                log(STALKER_A_PHONE, "wifi", lat, lon, ts, rssi=rng.randint(-72, -58))
            if rng.random() < 0.84:
                log(STALKER_A_WATCH, "bt",   lat, lon, ts, rssi=rng.randint(-78, -62))

        # Stalker B — solo, 80 % presence
        if minute >= 10 and idx in {0,1,2,3,5,6,7} and rng.random() < 0.80:
            log(STALKER_B_PHONE, "wifi", lat, lon, ts, rssi=rng.randint(-75, -60))

        # AirTag: 65 % of minutes
        if rng.random() < 0.65:
            log(AIRTAG, "bt", lat, lon, ts, rssi=rng.randint(-84, -68))

        # Car tracker: stops 0,1,3,5,6,7
        if idx in {0, 1, 3, 5, 6, 7} and rng.random() < 0.70:
            log(CAR_TRACKER, "bt", lat, lon, ts, rssi=rng.randint(-80, -65))

        # Suspicious solo devices
        for mac, stops in sus_stops.items():
            if idx in stops and rng.random() < 0.75:
                log(mac, rng.choice(["wifi", "bt"]), lat, lon, ts)

        # Own devices
        for mac, src in HOME_DEVICES:
            if mac in (MY_PHONE, MY_WATCH) and own.random() < 0.95:
                log(mac, src, lat, lon, ts, r=own)

    # Calibrate home (ignore home devices)
    macs_at_home = {r["mac"] for r in db.get_sightings_since(home_start)
                    if r["ts"] < walk_start}
    n_ignored = db.add_ignored(macs_at_home, "okolí doma", "baseline")

    # Run analysis + alerts
    persons = Analyzer(db).run(now=now)
    sent = Notifier(db, {"enabled": True, "cooldown_minutes": 0}).process(persons)

    suspicious = [p for p in persons if p["suspicious"]]
    print(f"✓ DB: {DB_PATH}")
    print(f"  Devices total : {len(db.get_all_devices())}")
    print(f"  Ignored       : {n_ignored}")
    print(f"  Persons       : {len(persons)}")
    print(f"  Suspicious    : {len(suspicious)}")
    print(f"  Alerts sent   : {len(sent)}")
    print()
    labels = {
        STALKER_A_PHONE: "Stalker A – phone",
        STALKER_A_WATCH: "Stalker A – watch",
        STALKER_B_PHONE: "Stalker B – phone",
        AIRTAG:          "Hidden AirTag",
        CAR_TRACKER:     "Car tracker",
        SUSPICIOUS_1:    "Suspicious device 1",
        SUSPICIOUS_2:    "Suspicious device 2",
        SUSPICIOUS_3:    "Suspicious device 3",
    }
    for p in persons[:10]:
        flag = " ⚠ SUSPICIOUS" if p["suspicious"] else ""
        cid  = f"cluster #{p['cluster_id']}" if p["cluster_id"] else "solo"
        print(f"  score={p['score']:.2f}  {cid}{flag}")
        for mac in p["macs"]:
            print(f"    {mac}  {labels.get(mac, '')}")


if __name__ == "__main__":
    main()
