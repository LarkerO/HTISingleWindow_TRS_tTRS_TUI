import httpx
import pytest

from ttrs.client import ProtocolError, TicketClient, load_stations
from ttrs.demo import DEMO_KEY, signed_response
from ttrs.domain import station_label, station_matches, stop_label
from ttrs.receipt import receipt_lines

STATION = {
    "id": "world:123",
    "name": "源站名",
    "name_zh": "测试车站",
    "name_en": "Example Central",
    "telegraph_code": "ABC",
    "operator_code": "OPER",
    "visible": True,
}


def test_dictionary_search_and_hidden_history():
    for query in ("abc", "ABC", "example", "测试", "cs", "world:123"):
        assert station_matches(STATION, query)
    assert not station_matches(STATION | {"visible": False}, "ABC")
    assert station_label(STATION) == "测试车站 (ABC)"
    stop = {"station_id": "world:123", "station": STATION | {"visible": False}}
    assert stop_label(stop, {"world:123": "旧站名"}) == "测试车站 (ABC)"
    ticket = {"coupons": [{"origin": stop, "destination": {"station_id": "other"}}]}
    assert any("测试车站 (ABC) → other" in line for line in receipt_lines(ticket, {}))


async def test_all_signed_station_pages_and_visibility():
    pages = []

    def handle(request):
        page = int(request.url.params["page"])
        pages.append(page)
        assert request.url.params["q"] == "测试"
        rows = [STATION | {"id": f"world:{page}"}]
        if page == 2:
            rows[0]["visible"] = False
        return signed_response(request, 200, {"data": rows, "total": 3, "limit": 1})

    client = TicketClient("http://test", DEMO_KEY, transport=httpx.MockTransport(handle))
    try:
        rows = await load_stations(client, "测试")
        assert pages == [1, 2, 3]
        assert [s["id"] for s in rows] == ["world:1", "world:3"]
    finally:
        await client.close()


async def test_incomplete_catalog_fails_instead_of_silently_truncating():
    client = TicketClient(
        "http://test",
        DEMO_KEY,
        transport=httpx.MockTransport(lambda r: signed_response(r, 200, {"data": [STATION], "total": 501})),
    )
    try:
        with pytest.raises(ProtocolError, match="分页"):
            await load_stations(client)
    finally:
        await client.close()


async def test_legacy_catalog_without_total():
    client = TicketClient(
        "http://test",
        DEMO_KEY,
        transport=httpx.MockTransport(
            lambda r: signed_response(r, 200, {"data": [{"id": "legacy", "name": "旧站"}]})
        ),
    )
    try:
        assert (await load_stations(client))[0]["id"] == "legacy"
    finally:
        await client.close()
