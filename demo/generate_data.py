"""Syntetická data: 10 minut doma, pak dvouhodinová procházka Prahou.

Scénář:
  - Doma: váš telefon a hodinky, televize, notebook a telefon souseda.
    Tato zařízení se odruší (calibrate_home) jako při hledání štěnic.
  - Vy jdete trasou přes 8 míst; váš telefon a hodinky jdou s vámi.
  - Kolemjdoucí: ~150 náhodných zařízení, každé vidět jen chvíli na jednom místě.
  - Soused v kavárně: zařízení vidět 25 minut, ale jen na jednom místě.
  - Sledující osoba: telefon + hodinky, vidět skoro všude; občas na pár minut
    zmizí z dosahu (obě zařízení najednou) → 1 skupina.
  - Skrytý BLE tracker (např. AirTag): vidět na většině míst.
"""
import random

ROUTE = [  # (lat, lon) – Praha
    (50.0870, 14.4208),  # Staroměstské náměstí
    (50.0865, 14.4114),  # Karlův most
    (50.0880, 14.4040),  # Malostranské náměstí
    (50.0905, 14.4005),  # Pražský hrad (cesta)
    (50.0833, 14.4030),  # Petřín
    (50.0810, 14.4135),  # Národní divadlo
    (50.0813, 14.4280),  # Václavské náměstí
    (50.0875, 14.4280),  # Prašná brána
]

FOLLOWER_PHONE = "3C:22:FB:11:22:33"
FOLLOWER_WATCH = "F4:5C:89:AA:BB:CC"
TRACKER = "D2:4E:7A:01:02:03"
NEIGHBOUR = "00:1A:2B:3C:4D:5E"

HOME = (50.0755, 14.4430)  # Vinohrady
MY_PHONE = "8A:1F:3E:44:55:66"
MY_WATCH = "C8:3A:35:10:20:30"
HOME_DEVICES = [  # (mac, zdroj, jde s vámi na procházku)
    (MY_PHONE, "wifi", True),
    (MY_WATCH, "bt", True),
    ("B8:27:EB:AA:00:01", "wifi", False),  # televize
    ("DC:A6:32:12:34:56", "wifi", False),  # notebook
    ("5E:77:21:9A:BC:DE", "bt", False),    # telefon souseda
]


def calibrate_home(db, info: dict) -> int:
    """Odruší vše, co bylo vidět doma před odchodem."""
    macs = {r["mac"] for r in db.get_sightings_since(info["home_start"])
            if r["ts"] < info["walk_start"]}
    return db.add_ignored(macs, "okolí doma", "baseline")


def rand_mac(rng: random.Random) -> str:
    first = rng.randrange(0, 256) | 0x02  # randomizovaná MAC
    return ":".join(f"{b:02X}" for b in [first & 0xFE] + [rng.randrange(256) for _ in range(5)])


def generate(db, start_ts: float, minutes: int = 120, seed: int = 42,
             home_minutes: int = 10) -> dict:
    rng = random.Random(seed)
    own = random.Random(seed + 1000)  # vlastní proud, aby se procházka neměnila
    per_stop = minutes / len(ROUTE)
    home_start = start_ts - home_minutes * 60

    def own_log(mac, source, lat, lon, ts):
        db.log_sighting(mac, source=source, rssi=own.randint(-55, -35),
                        lat=lat, lon=lon, ts=ts + own.uniform(0, 59))

    for minute in range(home_minutes):
        for mac, source, _ in HOME_DEVICES:
            if own.random() < 0.9:
                own_log(mac, source, *HOME, home_start + minute * 60)

    def position(minute: int):
        idx = min(int(minute // per_stop), len(ROUTE) - 1)
        lat, lon = ROUTE[idx]
        return idx, lat + rng.uniform(-0.0002, 0.0002), lon + rng.uniform(-0.0002, 0.0002)

    passers = [rand_mac(rng) for _ in range(150)]
    passer_slots = {m: (rng.randrange(minutes), rng.randint(1, 3)) for m in passers}
    neighbour_start = int(per_stop * 5)  # u Národního divadla

    count = 0
    follower_gap = 0
    for minute in range(minutes):
        idx, lat, lon = position(minute)
        ts = start_ts + minute * 60

        def log(mac, source, rssi):
            nonlocal count
            db.log_sighting(mac, source=source, rssi=rssi, lat=lat, lon=lon,
                            ts=ts + rng.uniform(0, 59))
            count += 1

        for mac, (start, dur) in passer_slots.items():
            if start <= minute < start + dur:
                log(mac, rng.choice(["wifi", "bt"]), rng.randint(-90, -60))

        if neighbour_start <= minute < neighbour_start + 25:
            log(NEIGHBOUR, "wifi", rng.randint(-70, -55))

        # Sledující drží odstup a občas na pár minut vypadne z dosahu;
        # telefon i hodinky přitom zmizí současně.
        if follower_gap > 0:
            follower_gap -= 1
        elif minute >= 5 and rng.random() < 0.07:
            follower_gap = rng.randint(2, 6)
        elif minute >= 5:
            if rng.random() < 0.85:
                log(FOLLOWER_PHONE, "wifi", rng.randint(-75, -60))
            if rng.random() < 0.8:
                log(FOLLOWER_WATCH, "bt", rng.randint(-80, -65))

        # Tracker: vidět v ~60 % minut
        if rng.random() < 0.6:
            log(TRACKER, "bt", rng.randint(-85, -70))

        # Vaše vlastní zařízení jsou s vámi pořád
        for mac, source, walks in HOME_DEVICES:
            if walks and own.random() < 0.95:
                own_log(mac, source, lat, lon, ts)

    return {"sightings": count, "passers": len(passers),
            "home_start": home_start, "walk_start": start_ts}
