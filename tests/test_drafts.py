import sqlite3

import pytest

from ttrs.store import Outbox


def sample(box, scope="agency"):
    return box.save_draft(
        scope,
        {"trip_id": 101, "origin_seq": 0, "destination_seq": 2, "passenger": "甲"},
        "G101 西安→南京",
        "甲",
        {"id": 101, "amount_minor": 12000, "available": 26},
    )


def test_draft_restart_version_conflict_and_single_promotion(tmp_path):
    path = tmp_path / "state.db"
    box = Outbox(path)
    key = sample(box)
    box.close()
    first, second = Outbox(path), Outbox(path)
    original = first.drafts("agency")[0]
    assert original["id"] == key
    assert first.drafts("other-agency") == []
    payload = {**original["payload"], "passenger": "乙"}
    first.edit_draft(key, "agency", 1, payload, "乙")
    with pytest.raises(ValueError, match="其他窗口"):
        second.promote_draft(key, "agency", 1)
    updated = second.drafts("agency")[0]
    assert updated["version"] == 2
    order = second.promote_draft(key, "agency", 2)
    with pytest.raises(ValueError):
        first.promote_draft(key, "agency", 2)
    assert first.drafts("agency") == []
    assert len(first.list("agency")) == 1
    assert first.get(order)["payload"] == payload
    assert first.get(order)["state"] == "pending"
    first.close()
    second.close()


def test_promotion_failure_rolls_back_draft_removal(tmp_path):
    box = Outbox(tmp_path / "state.db")
    key = sample(box)
    box.db.execute("""CREATE TRIGGER fail_order BEFORE INSERT ON orders
                      BEGIN SELECT RAISE(ABORT, 'simulated disk/database failure'); END""")
    box.db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        box.promote_draft(key, "agency", 1)
    assert box.drafts("agency")[0]["id"] == key
    assert box.list("agency") == []
    box.db.execute("DROP TRIGGER fail_order")
    box.db.commit()
    box.promote_draft(key, "agency", 1)
    assert box.drafts("agency") == []
    box.close()
