"""Backend HMAC-SM3-V1 protocol. Never log key material."""

import hashlib
import hmac
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass, field


class SignatureError(Exception):
    pass


def sm3(data: bytes) -> str:
    try:
        return hashlib.new("sm3", data).hexdigest()
    except ValueError:
        from gmssl.sm3 import sm3_hash

        return sm3_hash(list(data))


def mac(data: bytes, key: bytes) -> str:
    if len(key) > 64:
        key = bytes.fromhex(sm3(key))
    key = key.ljust(64, b"\0")
    inner = bytes(byte ^ 0x36 for byte in key)
    outer = bytes(byte ^ 0x5C for byte in key)
    return sm3(outer + bytes.fromhex(sm3(inner + data)))


@dataclass(frozen=True)
class SignedRequest:
    headers: dict[str, str] = field(repr=False)
    secret: bytes = field(repr=False)


def key_id(api_key: str) -> str:
    secret = hashlib.sha256(api_key.encode()).hexdigest()
    return sm3(("MTR-KEY-V1\n" + secret).encode())


def sign(api_key: str, method: str, target: str, body: bytes, extra: Mapping[str, str]) -> SignedRequest:
    secret = hashlib.sha256(api_key.encode()).hexdigest().encode("ascii")
    headers = {k.lower(): str(v) for k, v in extra.items()}
    headers.update(
        {
            "x-api-key-id": key_id(api_key),
            "x-timestamp": str(int(time.time())),
            "x-nonce": secrets.token_hex(16),
            "x-signature-algorithm": "HMAC-SM3-V1",
        }
    )
    canonical = "\n".join(
        [
            "MTR-HMAC-SM3-V1",
            headers["x-api-key-id"],
            method.upper(),
            target,
            headers["x-timestamp"],
            headers["x-nonce"],
            headers.get("content-type", "").strip().lower(),
            headers.get("x-agency-code", ""),
            headers.get("x-operator-code", ""),
            headers.get("idempotency-key", ""),
            sm3(body),
        ]
    )
    headers["x-signature"] = mac(canonical.encode(), secret)
    return SignedRequest(headers, secret)


def verify(status: int, headers: Mapping[str, str], body: bytes, request: SignedRequest) -> None:
    h = {k.lower(): v for k, v in headers.items()}
    stamp = h.get("x-response-timestamp", "")
    signature = h.get("x-response-signature", "")
    if (
        h.get("x-response-signature-algorithm") != "HMAC-SM3-V1"
        or not re.fullmatch(r"[0-9]{10}", stamp)
        or abs(time.time() - int(stamp)) > 300
        or not re.fullmatch(r"[a-f0-9]{64}", signature)
    ):
        raise SignatureError(f"响应签名缺失或过期（HTTP {status}）；请检查密钥、时钟和服务地址")
    metadata = [
        "x-request-id",
        "x-response-timestamp",
        "x-process-time-ms",
        "x-memory-delta-bytes",
        "x-memory-peak-bytes",
    ]
    if any(not h.get(k) for k in metadata):
        raise SignatureError("响应缺少签名元数据")
    canonical = "\n".join(
        [
            "MTR-HMAC-SM3-RESPONSE-V1",
            request.headers["x-signature"],
            request.headers["x-nonce"],
            str(status),
            *(h[k] for k in metadata),
            sm3(body),
        ]
    )
    if not hmac.compare_digest(signature, mac(canonical.encode(), request.secret)):
        raise SignatureError("响应 SM3 验签失败，未采用响应内容")
