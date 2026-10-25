import hashlib
import hmac
import json
import time

import httpx
import pytest

from ttrs.auth import SignatureError, mac, sign, sm3, verify
from ttrs.client import APIError, TicketClient
from ttrs.demo import DEMO_KEY, signed_response


def test_sm3_hmac_and_fallback(monkeypatch):
    assert sm3(b"abc") == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    original = hashlib.new
    for text in ["", "中文 / 🚆", "x" * 200]:
        for key in [b"a", "密钥".encode(), b"k" * 90]:
            expected = hmac.new(key, text.encode(), digestmod="sm3").hexdigest()
            assert mac(text.encode(), key) == expected

    def without_sm3(name, *args, **kwargs):
        if name == "sm3":
            raise ValueError("unsupported")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(hashlib, "new", without_sm3)
    assert sm3(b"abc") == "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0"
    assert mac("中文".encode(), b"k" * 90) == hmac.new(b"k" * 90, "中文".encode(), "sm3").hexdigest()


def test_request_canonical_matches_independent_openssl():
    body = '{"passenger":"中文🚆"}'.encode()
    target = "/api/v1/example?q=%E4%B8%AD&a=1&a=2"
    signed = sign(
        "fixture",
        "POST",
        target,
        body,
        {
            "Content-Type": "application/json",
            "X-Agency-Code": "LOCAL",
            "Idempotency-Key": "test-1",
        },
    )
    h = signed.headers
    secret = hashlib.sha256(b"fixture").hexdigest().encode()
    canonical = "\n".join(
        [
            "MTR-HMAC-SM3-V1",
            hashlib.new("sm3", b"MTR-KEY-V1\n" + secret).hexdigest(),
            "POST",
            target,
            h["x-timestamp"],
            h["x-nonce"],
            "application/json",
            "LOCAL",
            "",
            "test-1",
            hashlib.new("sm3", body).hexdigest(),
        ]
    )
    assert h["x-signature"] == hmac.new(secret, canonical.encode(), "sm3").hexdigest()
    assert "x-api-key" not in h
    assert "fixture" not in repr(signed)


@pytest.mark.asyncio
async def test_client_exact_wire_response_verification_and_errors():
    seen = []

    def handle(request):
        seen.append(request)
        secret = hashlib.sha256(DEMO_KEY.encode()).hexdigest().encode()
        h = request.headers
        canonical = "\n".join(
            [
                "MTR-HMAC-SM3-V1",
                h["x-api-key-id"],
                request.method,
                request.url.raw_path.decode(),
                h["x-timestamp"],
                h["x-nonce"],
                h.get("content-type", "").strip().lower(),
                h.get("x-agency-code", ""),
                "",
                h.get("idempotency-key", ""),
                hashlib.new("sm3", request.content).hexdigest(),
            ]
        )
        assert h["x-signature"] == hmac.new(secret, canonical.encode(), "sm3").hexdigest()
        return signed_response(request, 409, {"error": "库存冲突"})

    client = TicketClient("http://local.test", DEMO_KEY, "LOCAL", transport=httpx.MockTransport(handle))
    with pytest.raises(APIError, match="库存冲突"):
        await client.request(
            "POST",
            "/api/v1/tickets",
            payload={"passenger": "中文🚆"},
            params={"q": "中文", "a": "1 2"},
            idempotency_key="once",
        )
    assert json.loads(seen[0].content)["passenger"] == "中文🚆"
    assert "%E4%B8%AD" in seen[0].url.raw_path.decode()
    await client.close()

    client = TicketClient(
        "http://local.test",
        DEMO_KEY,
        transport=httpx.MockTransport(lambda r: httpx.Response(401, content=b"not JSON, not trusted")),
    )
    with pytest.raises(SignatureError):
        await client.request("GET", "/api/v1/me")
    await client.close()


def test_response_tampering_replay_and_expiry():
    signed = sign(DEMO_KEY, "GET", "/api/v1/me", b"", {})
    request = httpx.Request("GET", "http://demo.local/api/v1/me", headers=signed.headers)
    response = signed_response(request, 200, {"data": "中文"})
    verify(200, response.headers, response.content, signed)
    with pytest.raises(SignatureError):
        verify(200, response.headers, b"{}", signed)
    changed = dict(response.headers)
    changed["x-process-time-ms"] = "0"
    with pytest.raises(SignatureError):
        verify(200, changed, response.content, signed)
    changed = dict(response.headers)
    changed["x-response-timestamp"] = str(int(time.time()) - 301)
    with pytest.raises(SignatureError):
        verify(200, changed, response.content, signed)
    different = sign(DEMO_KEY, "GET", "/api/v1/me", b"", {})
    with pytest.raises(SignatureError):
        verify(200, response.headers, response.content, different)
