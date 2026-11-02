import random
import time

import pytest

from daemon.analyzer import Analyzer, cluster_devices, jaccard, phi
from daemon.database import Database
from daemon.gps_tracker import _nmea_to_decimal, _parse_gprmc
from daemon.notifier import Notifier
from demo.generate_data import (FOLLOWER_PHONE, FOLLOWER_WATCH, NEIGHBOUR,
                                TRACKER, calibrate_home, generate)
from web.app import create_app, is_randomized


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


NOW = (int(time.time()) // 60) * 60


@pytest.fixture
def demo_db(db):
    calibrate_home(db, generate(db, start_ts=NOW - 120 * 60))
    return db


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("offset", [0, 20, 40])
def test_tracker_never_merged_into_follower(tmp_path, seed, offset):
    db = Database(str(tmp_path / f"{seed}-{offset}.db"))
    generate(db, start_ts=NOW - 7200 + offset, seed=seed)
    persons = Analyzer(db).run(now=NOW + offset)
    tracker = next(p for p in persons if TRACKER in p["macs"])
    assert tracker["macs"] == [TRACKER]


def test_jaccard():
    assert jaccard({1, 2, 3}, {2, 3, 4}) == 0.5
    assert jaccard(set(), set()) == 0.0


PARAMS = dict(min_shared=5, min_phi=0.5, min_jaccard=0.9)


def test_phi():
    assert phi(set(range(10)), set(range(10)), 20) == pytest.approx(1.0)
    assert phi(set(range(10)), set(range(10, 20)), 20) == pytest.approx(-1.0)
    assert phi(set(range(20)), set(range(20)), 20) == 0.0  # bez rozptylu


def test_phone_and_watch_are_one_person():
    b = {"phone": set(range(20)), "watch": set(range(2, 20)), "other": {50, 51, 52}}
    assert cluster_devices(b, 60, **PARAMS) == [{"phone", "watch"}]


def test_clustering_is_transitive():
    b = {"a": set(range(0, 10)), "b": set(range(1, 11)), "c": set(range(2, 12))}
    assert cluster_devices(b, 60, **PARAMS) == [{"a", "b", "c"}]


def test_few_shared_windows_not_merged():
    b = {"a": {1, 2, 3, 4}, "b": {1, 2, 3, 4}}
    assert cluster_devices(b, 60, **PARAMS) == []


def test_frequent_but_independent_devices_not_merged():
    rng = random.Random(7)
    b = {m: {i for i in range(120) if rng.random() < 0.7} for m in ("a", "b")}
    assert jaccard(b["a"], b["b"]) > 0.5  # starý práh by je spojil
    assert cluster_devices(b, 120, **PARAMS) == []


def test_always_present_pair_merged_by_jaccard_fallback():
    b = {"a": set(range(60)), "b": set(range(1, 60))}
    assert cluster_devices(b, 60, **PARAMS) == [{"a", "b"}]


def test_follower_detected_as_single_group(demo_db):
    persons = Analyzer(demo_db).run()
    suspicious = [p for p in persons if p["suspicious"]]
    groups = [set(p["macs"]) for p in suspicious if p["cluster_id"]]
    assert {FOLLOWER_PHONE, FOLLOWER_WATCH} in groups


def test_independent_tracker_not_merged_with_follower(demo_db):
    persons = Analyzer(demo_db).run()
    tracker = next(p for p in persons if TRACKER in p["macs"])
    assert tracker["macs"] == [TRACKER]
    assert tracker["suspicious"]


def test_static_neighbour_and_passers_not_suspicious(demo_db):
    persons = Analyzer(demo_db).run()
    flagged = {m for p in persons if p["suspicious"] for m in p["macs"]}
    assert NEIGHBOUR not in flagged
    assert flagged == {FOLLOWER_PHONE, FOLLOWER_WATCH, TRACKER}


def test_ignore_list(demo_db):
    persons = Analyzer(demo_db, {"ignore_macs": [TRACKER.lower()]}).run()
    assert all(TRACKER not in p["macs"] for p in persons)


def test_cluster_id_stable_between_runs(demo_db):
    a = Analyzer(demo_db)
    first = next(p for p in a.run() if FOLLOWER_PHONE in p["macs"])["cluster_id"]
    second = next(p for p in a.run() if FOLLOWER_PHONE in p["macs"])["cluster_id"]
    assert first == second


def test_one_alert_per_person_with_cooldown(demo_db):
    persons = Analyzer(demo_db).run()
    n = Notifier(demo_db, {"enabled": True, "cooldown_minutes": 30})
    sent = n.process(persons)
    assert len(sent) == 2  # skupina sledujícího + tracker
    assert n.process(persons) == []


def test_dashboard_api_groups_devices(demo_db):
    Analyzer(demo_db).run()
    client = create_app(demo_db, {}).test_client()
    persons = client.get("/api/persons?suspicious=1").get_json()
    group = next(p for p in persons if p["cluster_id"])
    assert {d["mac"] for d in group["devices"]} == {FOLLOWER_PHONE, FOLLOWER_WATCH}
    stats = client.get("/api/stats").get_json()
    assert stats["groups"] == 1 and stats["suspicious"] == 2
    assert client.get("/").status_code == 200


def test_dashboard_requires_password_when_set(db):
    client = create_app(db, {"web": {"username": "u", "password": "tajne"}}).test_client()
    assert client.get("/api/stats").status_code == 401
    ok = client.get("/api/stats", auth=("u", "tajne"))
    assert ok.status_code == 200
    assert client.get("/api/stats", auth=("u", "spatne")).status_code == 401


def test_retention_purges_old_data(db):
    db.log_sighting("AA:AA:AA:AA:AA:AA", ts=time.time() - 30 * 86400)
    db.log_sighting("BB:BB:BB:BB:BB:BB")
    assert db.purge_older_than(14) == 1
    assert [r["mac"] for r in db.get_all_devices()] == ["BB:BB:BB:BB:BB:BB"]


def test_randomized_mac():
    assert is_randomized("D2:4E:7A:01:02:03")
    assert not is_randomized("00:1A:2B:3C:4D:5E")


def test_nmea_parsing():
    assert _nmea_to_decimal("5005.2200", "N") == pytest.approx(50.087)
    s = "$GPRMC,123519,A,5005.2200,N,01425.2480,E,0.0,0.0,011126,,"
    lat, lon = _parse_gprmc(s)
    assert lat == pytest.approx(50.087) and lon == pytest.approx(14.4208)
    assert _parse_gprmc("$GPRMC,123519,V,,,,,,,,,") is None
