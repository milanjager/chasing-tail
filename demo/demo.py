"""Demo v terminálu: vygeneruje procházku, spustí analýzu a vypíše výsledky.

Spuštění (bez RPi, bez root):
  python -m demo.demo                 # s odrušením okolí doma
  python -m demo.demo --bez-odruseni  # ukáže, co se stane bez odrušení
"""
import argparse
import tempfile
import time
from pathlib import Path

from daemon.analyzer import Analyzer
from daemon.database import Database
from daemon.notifier import Notifier
from demo.generate_data import (FOLLOWER_PHONE, FOLLOWER_WATCH, MY_PHONE, MY_WATCH,
                                NEIGHBOUR, TRACKER, calibrate_home, generate)

LABELS = {
    FOLLOWER_PHONE: "sledující – telefon",
    FOLLOWER_WATCH: "sledující – hodinky",
    TRACKER: "skrytý BLE tracker",
    NEIGHBOUR: "soused v kavárně",
    MY_PHONE: "VÁŠ telefon",
    MY_WATCH: "VAŠE hodinky",
}


def build_demo_db(path: str, calibrate: bool = True) -> Database:
    db = Database(path)
    info = generate(db, start_ts=time.time() - 120 * 60)
    print(f"Vygenerováno {info['sightings']} záznamů, {info['passers']} kolemjdoucích.")
    if calibrate:
        n = calibrate_home(db, info)
        print(f"Odrušeno {n} zařízení z domova (váš telefon, hodinky, TV, notebook, soused).\n")
    else:
        print("Bez odrušení okolí.\n")
    return db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bez-odruseni", action="store_true", help="nespouštět odrušení okolí")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp()) / "demo.db"
    db = build_demo_db(str(tmp), calibrate=not args.bez_odruseni)
    persons = Analyzer(db).run()
    sent = Notifier(db, {"enabled": True, "cooldown_minutes": 30}).process(persons)

    print(f"{'Osoba':<14}{'Skóre':>7}  Zařízení")
    print("-" * 70)
    for p in persons[:8]:
        who = f"skupina #{p['cluster_id']}" if p["cluster_id"] else "samostatné"
        flag = "  ⚠" if p["suspicious"] else ""
        print(f"{who:<14}{p['score']:>7.2f}  {p['macs'][0]}  {LABELS.get(p['macs'][0], '')}{flag}")
        for mac in p["macs"][1:]:
            print(f"{'':<23}{mac}  {LABELS.get(mac, '')}")

    print(f"\nUpozornění ({len(sent)}):")
    for m in sent:
        print("  •", m)
    print(f"\nDatabáze: {tmp}")


if __name__ == "__main__":
    main()
