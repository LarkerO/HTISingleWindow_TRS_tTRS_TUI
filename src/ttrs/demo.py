"""In-process, signed demonstration API. Never contacts a real service."""

import hashlib
import json
import time
from copy import deepcopy

import httpx

from .auth import mac, sm3

DEMO_KEY = "ttrs-local-demonstration-only"
STATIONS = [
    {"id": "minecraft/overworld:9223372036854775701", "name": "西安", "dimension": "minecraft/overworld"},
    {"id": "minecraft/overworld:9223372036854775702", "name": "郑州", "dimension": "minecraft/overworld"},
    {"id": "minecraft/overworld:9223372036854775703", "name": "南京", "dimension": "minecraft/overworld"},
]


def signed_response(request: httpx.Request, status: int, data: dict, key: str = DEMO_KEY) -> httpx.Response:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {
        "x-request-id": "d" * 32,
        "x-response-timestamp": str(int(time.time())),
        "x-process-time-ms": "0.5",
        "x-memory-delta-bytes": "0",
        "x-memory-peak-bytes": "1024",
        "x-response-signature-algorithm": "HMAC-SM3-V1",
        "content-type": "application/json",
    }
    canonical = "\n".join(
        [
            "MTR-HMAC-SM3-RESPONSE-V1",
            request.headers["x-signature"],
            request.headers["x-nonce"],
            str(status),
            headers["x-request-id"],
            headers["x-response-timestamp"],
            headers["x-process-time-ms"],
            headers["x-memory-delta-bytes"],
            headers["x-memory-peak-bytes"],
            sm3(raw),
        ]
    )
    headers["x-response-signature"] = mac(
        canonical.encode(), hashlib.sha256(key.encode()).hexdigest().encode()
    )
    return httpx.Response(status, content=raw, headers=headers)


class DemoServer:
    def __init__(self):
        self.orders: dict[str, tuple[dict, dict]] = {}
        self.tickets: dict[str, dict] = {}
        self.documents = [
            {
                "id": 1,
                "document_type": "ID_CARD",
                "document_number": "DEMO0001",
                "issuing_country": "CHN",
                "birth_date": "1990-01-01",
                "surname": None,
                "given_name": "演示旅客",
                "display_name": "演示旅客",
                "version": 1,
            }
        ]
        self.quotes = {}
        self.variants = {}
        self.next_trip = 200
        self.date = ""
        self.origin = STATIONS[0]["id"]
        self.destination = STATIONS[2]["id"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        status = 200
        if path.endswith("/me"):
            result = {
                "role": "agency",
                "agency_code": "DEMO",
                "agency": {"name": "本地演示出票方", "code": "DEMO"},
            }
        elif path.endswith("/stations"):
            q = request.url.params.get("q", "")
            result = [s for s in STATIONS if q in s["name"]]
        elif path.endswith("/journeys"):
            self.date = request.url.params["date"]
            self.origin = request.url.params["origin"]
            self.destination = request.url.params["destination"]
            used = sum(t["status"] == "OPEN" for t in self.tickets.values())
            result = [
                {
                    "id": i,
                    "train_number": train,
                    "name": train + "|演示线路",
                    "operator_code": "DEMO",
                    "origin_seq": 0,
                    "destination_seq": 2,
                    "departure_at": self.date + " " + depart,
                    "arrival_at": self.date + " " + arrive,
                    "available": max(0, 26 - used),
                    "amount_minor": fare,
                    "currency": "CNY",
                    "fare_available": True,
                    "fare_version": 1,
                }
                for i, train, depart, arrive, fare in [
                    (101, "G101", "08:30:00", "11:20:00", 12000),
                    (102, "D202", "10:10:00", "14:35:00", 8650),
                ]
            ]
            earliest = request.url.params.get("time_from", "")
            if earliest:
                result.append(
                    {
                        **result[0],
                        "id": 103,
                        "train_number": "G303",
                        "departure_at": self.date + " 16:00:00",
                        "arrival_at": self.date + " 18:50:00",
                    }
                )
                result = [j for j in result if j["departure_at"][11:] >= earliest]
            wanted = request.url.params.get("train_number", "")
            if wanted:
                result = [j for j in result if j["train_number"] == wanted]
            for journey in result:
                variant = (self.date, self.origin, self.destination, journey["id"])
                if variant not in self.variants:
                    if journey["id"] not in self.quotes:
                        self.variants[variant] = journey["id"]
                    else:
                        self.next_trip += 1
                        self.variants[variant] = self.next_trip
                journey["id"] = self.variants[variant]
                self.quotes[journey["id"]] = {
                    "journey": deepcopy(journey),
                    "origin": self.origin,
                    "destination": self.destination,
                }
        elif "/trips/" in path:
            result = {
                "id": int(path.rsplit("/", 1)[1]),
                "stops": [
                    {
                        "seq": i,
                        "station_id": s["id"],
                        "name": s["name"],
                        "arrival_at": self.date + f" {8 + i:02}:30:00",
                        "departure_at": self.date + f" {8 + i:02}:32:00",
                    }
                    for i, s in enumerate(STATIONS)
                ],
            }
        elif path.endswith("/passenger-documents") and request.method == "GET":
            result = [
                d
                for d in self.documents
                if all(
                    str(d.get(k, "")).casefold() == v.casefold()
                    for k, v in request.url.params.items()
                    if k != "page"
                )
            ]
        elif path.endswith("/passenger-documents") and request.method == "POST":
            result = {
                **body,
                "id": len(self.documents) + 1,
                "version": 1,
                "display_name": " ".join(v for v in [body.get("surname"), body["given_name"]] if v),
            }
            if any(
                all(
                    d.get(k) == result.get(k) for k in ("document_type", "issuing_country", "document_number")
                )
                for d in self.documents
            ):
                return signed_response(request, 409, {"error": "证件已存在"})
            self.documents.append(result)
            status = 201
        elif path.endswith("/tickets") and request.method == "POST":
            idem = request.headers["idempotency-key"]
            if idem in self.orders:
                old, ticket = self.orders[idem]
                if old != body:
                    return signed_response(request, 409, {"error": "幂等键与原参数不同"})
                result = ticket
            else:
                number = f"999{len(self.tickets) + 1:010}"
                doc = next((d for d in self.documents if d["id"] == body.get("document_id")), None)
                quote = self.quotes.get(body["trip_id"], {})
                journey = quote.get("journey", {})
                result = {
                    "issued_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
                    "ticket_number": number,
                    "pnr": "DEMO01",
                    "status": "OPEN",
                    "agency_code": "DEMO",
                    "passenger": doc["display_name"] if doc else body["passenger"],
                    "amount_minor": journey.get(
                        "amount_minor", 12000 if body["trip_id"] in {101, 103} else 8650
                    ),
                    "currency": "CNY",
                    "coupons": [
                        {
                            "trip": {"train_number": journey.get("train_number"), "operator_code": "DEMO"},
                            "origin": {
                                "station_id": quote.get("origin", self.origin),
                                "departure_at": journey.get("departure_at", "未提供"),
                            },
                            "destination": {
                                "station_id": quote.get("destination", self.destination),
                                "arrival_at": journey.get("arrival_at", "未提供"),
                            },
                            "trip_id": body["trip_id"],
                            "origin_seq": body["origin_seq"],
                            "destination_seq": body["destination_seq"],
                        }
                    ],
                }
                self.orders[idem] = (deepcopy(body), result)
                self.tickets[number] = result
            status = 201
        elif "/tickets/" in path:
            number = path.split("/tickets/")[1].split("/")[0]
            if number not in self.tickets:
                return signed_response(request, 404, {"error": "演示客票不存在"})
            result = self.tickets[number]
            if path.endswith("/refund"):
                result["status"] = "RFND"
        else:
            return signed_response(request, 404, {"error": "演示接口未实现"})
        return signed_response(request, status, {"data": result, "timezone": "UTC"})
