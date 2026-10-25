"""Read-only live check. Supply key via environment; never prints credentials."""

import asyncio
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
if os.name == "nt" and sys.prefix == sys.base_prefix and (root / ".deps").is_dir():
    sys.path.insert(0, str(root / ".deps"))

from ttrs.client import TicketClient


async def main():
    client = TicketClient(
        os.environ.get("TTRS_BASE_URL", "http://127.0.0.1:8000"),
        os.environ.get("TICKETING_API_KEY", ""),
        os.environ.get("TTRS_AGENCY_CODE", ""),
    )
    try:
        me = (await client.request("GET", "/api/v1/me"))["data"]
        print("PASS signed identity:", me["role"])
        stations = (await client.request("GET", "/api/v1/stations"))["data"]
        print("PASS signed stations:", len(stations))
        trips = (await client.request("GET", "/api/v1/trips", params={"page": 1}))["data"]
        print("PASS signed trips:", len(trips))
        if trips:
            trip = (await client.request("GET", f"/api/v1/trips/{int(trips[0]['id'])}"))["data"]
            stops = trip.get("stops", [])
            print("PASS signed trip detail:", len(stops), "stops")
            if len(stops) > 1 and stops[0]["station_id"] != stops[-1]["station_id"]:
                date = str(stops[0]["departure_at"])[:10]
                journeys = (
                    await client.request(
                        "GET",
                        "/api/v1/journeys",
                        params={
                            "origin": stops[0]["station_id"],
                            "destination": stops[-1]["station_id"],
                            "date": date,
                        },
                    )
                )["data"]
                print("PASS signed journeys:", len(journeys))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
