import sqlite3

from ttrs.store import Outbox


def test_existing_database_upgrade_failure_states_and_recovery(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE orders (
        id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL, label TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', ticket TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
    db.execute("INSERT INTO orders(id,scope,payload,label) VALUES('old','agency','{}','legacy')")
    db.commit()
    db.close()
    box = Outbox(path)
    assert box.get("old")["last_error"] is None
    payload = {"trip_id": 101, "origin_seq": 0, "destination_seq": 2, "passenger": "旅客"}
    key = box.prepare("agency", payload, "G101")
    box.failed(key, "HTTP 409: 票价版本变化", refused=True)
    assert box.get(key)["state"] == "blocked"
    box.close()
    box = Outbox(path)
    assert box.get(key)["last_error"] == "HTTP 409: 票价版本变化"
    box.started(key)
    box.failed(key, "网络中断")
    assert box.get(key)["state"] == "pending"
    assert box.get(key)["payload"] == payload
    box.complete(key, {"ticket_number": "9990000000001", "status": "OPEN"})
    box.failed(key, "late error", refused=True)
    assert box.get(key)["state"] == "issued"
    assert box.get(key)["last_error"] is None
    box.close()
