import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from rich.cells import cell_len

from ttrs.auth import SignatureError
from ttrs.client import ConnectionMetrics, TicketClient
from ttrs.demo import DEMO_KEY, signed_response
from ttrs.runtime import Usage, format_status


def test_runtime_status_uses_local_offset_and_real_metric_scopes():
    metrics = ConnectionMetrics(
        reachable=True, trusted=True, health_ok=True, roundtrip_ms=12.34, server_ms=1.25
    )
    now = datetime(2026, 10, 26, 12, 34, 56, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    text = format_status(Usage(3.5, 32 * 1024**2), metrics, "0010000000001", 17, now=now)
    assert "2026-10-26 12:34:56 +0530" in text
    assert "下一张票号 出票时生成" in text
    assert "0010000000001" in text
    assert "累计操作 17" in text
    assert "客户端CPU 3.5%" in text and "内存RSS 32.0MiB" in text
    assert "12.34ms" in text and "1.25ms" in text
    assert max(cell_len(line) for line in text.splitlines()) <= 78
    local = format_status(Usage(), metrics, "待生成", 0, local=True, now=now)
    assert "网络 本地" in local
    assert "演示" not in local and "测试" not in local
    assert "12.34ms" not in local and "1.25ms" not in local


async def test_heartbeat_preserves_signed_processing_metrics_and_recovers():
    offline = False

    def handler(request):
        if offline:
            raise httpx.ConnectError("offline", request=request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return signed_response(request, 200, {"data": {}})

    client = TicketClient("http://test.local", DEMO_KEY, transport=httpx.MockTransport(handler))
    await client.request("GET", "/api/v1/me")
    assert client.metrics.server_ms == 0.5
    assert client.metrics.label == "已连接"
    await client.probe()
    assert client.metrics.server_ms == 0.5
    offline = True
    await client.probe()
    assert client.metrics.label == "断开"
    assert client.metrics.roundtrip_ms is None
    offline = False
    await client.probe()
    assert client.metrics.label == "已连接"
    assert client.metrics.roundtrip_ms is not None
    await client.close()


async def test_unsigned_metrics_are_never_used_as_processing_time():
    client = TicketClient(
        "http://test.local",
        DEMO_KEY,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"data": {}}, headers={"X-Process-Time-Ms": "999"})
        ),
    )
    with pytest.raises(SignatureError):
        await client.request("GET", "/api/v1/me")
    assert client.metrics.label == "验签异常"
    assert client.metrics.server_ms is None
    await client.close()


async def test_late_heartbeat_cannot_override_new_business_response():
    started, release = asyncio.Event(), asyncio.Event()

    async def handler(request):
        if request.url.path == "/health":
            started.set()
            await release.wait()
            return httpx.Response(503, json={"error": "late"})
        return signed_response(request, 200, {"data": {}})

    client = TicketClient("http://test.local", DEMO_KEY, transport=httpx.MockTransport(handler))
    probe = asyncio.create_task(client.probe())
    await started.wait()
    await client.request("GET", "/api/v1/me")
    release.set()
    await probe
    assert client.metrics.label == "已连接"
    assert client.metrics.server_ms == 0.5
    await client.close()
