"""Sign the exact HTTPX URL and body; verify raw response before JSON."""

import json
import math
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from .auth import SignatureError, sign, verify


class ProtocolError(ValueError):
    pass


class APIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def normalize_base(value: str) -> str:
    value = value.strip().rstrip("/")
    url = urlsplit(value)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("服务地址应为 http(s)://主机[:端口]，不含路径、账户或查询串")
    return value


@dataclass
class ConnectionMetrics:
    reachable: bool | None = None
    trusted: bool | None = None
    health_ok: bool | None = None
    roundtrip_ms: float | None = None
    server_ms: float | None = None

    @property
    def label(self) -> str:
        if self.reachable is None:
            return "未连接"
        if not self.reachable:
            return "断开"
        if self.health_ok is False:
            return "服务异常"
        if self.trusted is False:
            return "验签异常"
        return "已连接"


def server_duration(value: str | None) -> float | None:
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


class TicketClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        agency: str = "",
        timeout: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.metrics = ConnectionMetrics()
        self._api_generation = 0
        self.base_url = normalize_base(base_url)
        if not api_key.strip():
            raise ValueError("请输入 API 密钥")
        self.api_key = api_key
        self.agency = agency.strip()
        self.http = httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout, follow_redirects=False, transport=transport
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def probe(self) -> None:
        """Reachability only: never overwrites a signed business processing duration."""
        if self.http.is_closed:
            return
        generation = self._api_generation
        started = time.perf_counter()
        try:
            response = await self.http.get("/health", timeout=3)
            try:
                body = response.json()
            except ValueError:
                body = None
            if generation == self._api_generation:
                self.metrics.reachable = True
                self.metrics.health_ok = (
                    response.status_code == 200 and isinstance(body, dict) and body.get("status") == "ok"
                )
                self.metrics.roundtrip_ms = (time.perf_counter() - started) * 1000
        except httpx.HTTPError:
            if generation == self._api_generation:
                self.metrics.reachable = False
                self.metrics.roundtrip_ms = None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        payload: dict | None = None,
        idempotency_key: str = "",
    ) -> dict:
        if not path.startswith("/api/v1/") or "#" in path or "?" in path:
            raise ValueError("非法业务接口路径")
        body = (
            b""
            if payload is None
            else json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
        )
        extra = {"Accept": "application/json"}
        if payload is not None:
            extra["Content-Type"] = "application/json"
        if self.agency:
            extra["X-Agency-Code"] = self.agency
        if idempotency_key:
            extra["Idempotency-Key"] = idempotency_key
        request = self.http.build_request(method, path, params=params, content=body)
        signed = sign(self.api_key, method, request.url.raw_path.decode("ascii"), body, extra)
        request.headers.update(signed.headers)
        self._api_generation += 1
        generation = self._api_generation
        started = time.perf_counter()
        try:
            response = await self.http.send(request)
        except httpx.HTTPError:
            if generation == self._api_generation:
                self.metrics.reachable = False
                self.metrics.roundtrip_ms = None
                self.metrics.server_ms = None
            raise
        elapsed = (time.perf_counter() - started) * 1000
        try:
            verify(response.status_code, response.headers, response.content, signed)
        except SignatureError:
            if generation == self._api_generation:
                self.metrics.reachable, self.metrics.trusted = True, False
                self.metrics.health_ok = None
                self.metrics.roundtrip_ms, self.metrics.server_ms = elapsed, None
            raise
        if generation == self._api_generation:
            self.metrics.reachable = self.metrics.trusted = self.metrics.health_ok = True
            self.metrics.roundtrip_ms = elapsed
            self.metrics.server_ms = server_duration(response.headers.get("x-process-time-ms"))
        try:
            result = response.json()
        except ValueError as exc:
            raise ValueError("已验签响应不是合法 JSON") from exc
        if not isinstance(result, dict):
            raise ProtocolError("已验签响应结构不正确")
        if response.is_error:
            raise APIError(response.status_code, str(result.get("error", "请求失败")))
        if response.status_code not in {200, 201}:
            raise ValueError(f"非预期 HTTP 状态 {response.status_code}")
        return result
