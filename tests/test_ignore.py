import time

import pytest

from daemon.analyzer import Analyzer
from daemon.database import Database
from demo.generate_data import (FOLLOWER_PHONE, FOLLOWER_WATCH, HOME_DEVICES, MY_PHONE,
                                MY_WATCH, TRACKER, calibrate_home, generate)
from web.app import create_app

NOW = (int(time.time()) // 60) * 60
HOME_MACS = {m for m, _, _ in HOME_DEVICES}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def walk(db):
    return generate(db, start_ts=NOW - 120 * 60)


@pytest.fixture
def client(db):
    return create_app(db, {}).test_client()


def flagged(db):
    return {m for p in Analyzer(db).run(now=NOW) if p["suspicious"] for m in p["macs"]}


def test_own_devices_look_like_followers_without_calibration(db, walk):
    assert {MY_PHONE, MY_WATCH} <= flagged(db)


def test_calibration_at_home_removes_own_devices(db, walk):
    assert calibrate_home(db, walk) == len(HOME_MACS)
    assert flagged(db) == {FOLLOWER_PHONE, FOLLOWER_WATCH, TRACKER}


def test_add_ignored_is_idempotent_and_case_insensitive(db):
    assert db.add_ignored(["aa:bb:cc:dd:ee:ff"], "moje", "manual") == 1
    assert db.add_ignored(["AA:BB:CC:DD:EE:FF"], "znovu", "manual") == 0
    assert db.get_ignored_macs() == {"AA:BB:CC:DD:EE:FF"}


def test_ambient_ignore_takes_only_recent_devices(db, client):
    db.log_sighting("11:11:11:11:11:11", ts=time.time() - 3600)
    db.log_sighting("22:22:22:22:22:22", ts=time.time() - 60)
    db.log_sighting("33:33:33:33:33:33", ts=time.time() - 30)
    assert client.get("/api/ambient?minutes=5").get_json()["count"] == 2
    r = client.post("/api/ambient/ignore", json={"minutes": 5}).get_json()
    assert r["added"] == 2
    assert db.get_ignored_macs() == {"22:22:22:22:22:22", "33:33:33:33:33:33"}
    assert client.get("/api/ambient?minutes=5").get_json()["count"] == 0


def test_clear_ambient_keeps_manual_entries(db, client):
    db.add_ignored(["22:22:22:22:22:22"], "okolí", "baseline")
    db.add_ignored(["44:44:44:44:44:44"], "moje hodinky", "manual")
    assert client.delete("/api/ambient").get_json()["removed"] == 1
    assert db.get_ignored_macs() == {"44:44:44:44:44:44"}


def test_manual_add_validates_mac(client, db):
    assert client.post("/api/ignored", json={"macs": ["nesmysl"]}).status_code == 400
    assert client.post("/api/ignored", json={"macs": "AA:BB:CC:DD:EE:FF"}).status_code == 400
    ok = client.post("/api/ignored", json={"macs": ["aa-bb-cc-dd-ee-ff"], "label": "x" * 100})
    assert ok.get_json()["added"] == 1
    row = client.get("/api/ignored").get_json()[0]
    assert row["mac"] == "AA:BB:CC:DD:EE:FF" and len(row["label"]) == 60


def test_writes_require_json(client):
    r = client.post("/api/ambient/ignore", data="minutes=5",
                    content_type="application/x-www-form-urlencoded")
    assert r.status_code == 415


def test_ignored_hidden_from_dashboard_and_restorable(db, walk, client):
    calibrate_home(db, walk)
    Analyzer(db).run(now=NOW)
    macs = lambda: {d["mac"] for p in client.get("/api/persons").get_json() for d in p["devices"]}
    assert MY_PHONE not in macs()
    client.post("/api/ignored", json={"macs": [TRACKER]})
    assert TRACKER not in macs()
    assert client.get("/api/stats").get_json()["ignored"] == len(HOME_MACS) + 1
    client.delete(f"/api/ignored/{TRACKER}")
    assert TRACKER in macs()
