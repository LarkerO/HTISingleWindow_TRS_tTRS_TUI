import pytest

from ttrs.domain import money, parse_date, sale_payload, station_matches


def test_dates_money_and_chinese_lookup():
    assert parse_date("20261026") == "2026-10-26"
    with pytest.raises(ValueError):
        parse_date("20260230")
    assert money(125) == "1.25 CNY"
    assert money(None) == "未报价"
    station = {"id": "world:9223372036854775807", "name": "西安"}
    for query in ["西", "xian", "xa", "9223372036854775807"]:
        assert station_matches(station, query)


def test_payload_uses_exact_sequence_document_and_fare_version():
    journey = {
        "id": "123",
        "origin_seq": "7",
        "destination_seq": "9",
        "available": "2",
        "amount_minor": "125",
        "fare_version": "5",
    }
    assert sale_payload(journey, "", "456") == {
        "trip_id": 123,
        "origin_seq": 7,
        "destination_seq": 9,
        "document_id": 456,
        "fare_version": 5,
    }
    with pytest.raises(ValueError):
        sale_payload({**journey, "available": 0}, "旅客")
    with pytest.raises(ValueError):
        sale_payload({**journey, "amount_minor": None}, "旅客")
    with pytest.raises(ValueError):
        sale_payload(journey, "旅客", "-1")


def test_travel_date_shortcuts_use_next_utc_day():
    from datetime import date

    from ttrs.domain import parse_travel_date

    ref = date(2026, 10, 26)
    assert parse_travel_date("30", ref) == "2026-10-30"
    assert parse_travel_date("20", ref) == "2026-11-20"
    assert parse_travel_date("+1", ref) == "2026-10-27"
    assert parse_travel_date("31", date(2026, 2, 1)) == "2026-03-31"
    assert parse_travel_date("20261004", ref) == "2026-10-04"
    with pytest.raises(ValueError):
        parse_travel_date("0", ref)
    with pytest.raises(ValueError):
        parse_travel_date("+366", ref)
