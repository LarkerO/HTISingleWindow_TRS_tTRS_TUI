import pytest

from ttrs.flow import JourneyFlow

A = {"id": "a", "name": "甲"}
B = {"id": "b", "name": "乙"}


def test_roundtrip_and_cross_midnight_bound():
    flow = JourneyFlow()
    flow.reset("roundtrip")
    assert flow.advance(A, B, "2026-10-27 00:20:00.500") == (B, A)
    assert flow.window("2026-10-27") == {"time_from": "00:20:00"}
    with pytest.raises(ValueError, match="上一程到达日期"):
        flow.window("2026-10-26")
    assert not flow.accepts("2026-10-27 00:20:00.100")
    assert flow.accepts("2026-10-27 00:20:00.500")
    assert flow.window("2026-10-28") == {}
    assert flow.advance(B, A, "2026-10-28 11:00:00") is None
    assert flow.mode == "normal"
    assert flow.earliest is None


def test_connection_keeps_next_origin_and_can_reset():
    flow = JourneyFlow()
    flow.reset("connection")
    origin, destination = flow.advance(A, B, "2026-10-26 12:00:00")
    assert origin == B and destination is None
    origin["name"] = "changed"
    assert B["name"] == "乙"
    flow.reset()
    assert flow.accepts("2026-10-01 00:00:00")
