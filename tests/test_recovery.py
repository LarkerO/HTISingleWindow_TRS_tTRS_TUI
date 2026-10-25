import httpx
import pytest

from ttrs.client import TicketClient
from ttrs.demo import DEMO_KEY, DemoServer
from ttrs.store import Outbox


async def test_lost_response_restart_same_order_never_double_issues(tmp_path):
    server = DemoServer()
    requests = []
    drop = True

    def handler(request):
        nonlocal drop
        requests.append(request)
        reply = server.handle(request)  # Server commits BEFORE the connection is lost.
        if drop:
            drop = False
            raise httpx.ReadTimeout("lost response", request=request)
        return reply

    path = tmp_path / "orders.sqlite3"
    box = Outbox(path)
    payload = {"trip_id": 101, "origin_seq": 0, "destination_seq": 2, "passenger": "旅客"}
    key = box.prepare("agency-a", payload, "G101 西安→南京")
    client = TicketClient("http://test.local", DEMO_KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(httpx.ReadTimeout):
        await client.request("POST", "/api/v1/tickets", payload=payload, idempotency_key=key)
    assert len(server.tickets) == 1
    box.close()  # Simulate a client process restart.
    box = Outbox(path)
    recovered = box.list("agency-a")[0]
    assert box.list("agency-b") == []
    assert recovered["state"] == "pending"
    reply = await client.request(
        "POST", "/api/v1/tickets", payload=recovered["payload"], idempotency_key=recovered["id"]
    )
    box.complete(key, reply["data"])
    assert len(server.tickets) == 1
    assert requests[0].content == requests[1].content
    assert requests[0].headers["idempotency-key"] == requests[1].headers["idempotency-key"]
    assert requests[0].headers["x-nonce"] != requests[1].headers["x-nonce"]
    assert box.get(key)["ticket"]["ticket_number"] == "9990000000001"
    await client.close()
    box.close()
