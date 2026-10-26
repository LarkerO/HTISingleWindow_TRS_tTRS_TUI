"""Exercise the real PHP API and the actual TUI using dedicated, cleaned test records.

Run in Debian with PHP and the tTRS dev environment. No real API keys are printed.
Uses the existing backend passenger fixture; existing business rows are not changed.
"""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

import httpx
from textual.widgets import DataTable, Input, Static

from ttrs import APP_TITLE
from ttrs.app import TicketApp
from ttrs.client import TicketClient, load_stations
from ttrs.config import Config
from ttrs.screens import ChoiceScreen, FormScreen, MessageScreen, ReceiptScreen, StationScreen

backend = Path(os.environ.get("TTRS_BACKEND_DIR", root.parent / "backend")).expanduser().resolve()
fixture_script = backend / "tests" / "passenger-fixture.php"


def php_fixture(action: str, suffix: str) -> dict:
    reply = subprocess.run(
        ["php", str(fixture_script), action, suffix], cwd=backend, capture_output=True, text=True, check=True
    )
    return json.loads(reply.stdout)


async def until(pilot, predicate, stage: str) -> None:
    for _ in range(400):
        await pilot.pause(0.02)
        if predicate():
            return
    raise RuntimeError("TUI stage did not complete: " + stage)


async def exercise(base: str, fixture: dict, data: Path, checks: list[str]) -> None:
    client = TicketClient(base, fixture["agency_key"])
    try:
        identity = (await client.request("GET", "/api/v1/me"))["data"]
        assert identity["agency_code"] == fixture["agency"]
        checks.append("real signed agency authentication")
        stations = await load_stations(client)
        assert any(s["id"] == fixture["origin"] for s in stations)
        checks.append("real signed station catalog")
        params = {
            "origin": fixture["origin_code"].lower(),
            "destination": fixture["destination_code"],
            "date": fixture["date"],
        }

        async def quote():
            result = (await client.request("GET", "/api/v1/journeys", params=params))["data"]
            return next(j for j in result if int(j["id"]) == fixture["trip_id"])

        before = await quote()
        assert int(before["available"]) == 10
        assert client.metrics.server_ms is not None
        assert client.metrics.roundtrip_ms is not None
        processing = client.metrics.server_ms
        await client.probe()
        assert client.metrics.label == "已连接"
        assert client.metrics.server_ms == processing
        checks.append("real interval fare and inventory query")
        doc = {
            **{k: fixture["document"][k] for k in ("document_type", "issuing_country", "birth_date")},
            "document_number": fixture["document"]["document_number"] + "-EXTRA",
            "surname": None,
            "given_name": "tTRS 实机联调旅客",
            "reason": "Isolated tTRS end-to-end check",
        }
        saved = (await client.request("POST", "/api/v1/passenger-documents", payload=doc))["data"]
        checks.append("real passenger document registration")
        app = TicketApp(Config(base_url=base), store_path=data / "orders.sqlite3")
        async with app.run_test(size=(120, 36)) as pilot:
            assert app.title == app.config.window_title
            assert APP_TITLE in str(app.query_one("#identity", Static).content)
            await pilot.press("ctrl+o")
            await until(pilot, lambda: isinstance(app.screen, FormScreen), "connection form")
            app.screen.query_one("#key", Input).value = fixture["agency_key"]
            await pilot.press("f8")
            await until(pilot, lambda: not app.busy, "connect to actual backend")
            assert app.client is not None
            assert APP_TITLE in str(app.query_one("#identity", Static).render())
            checks.append("actual TUI connects to real backend")
            for key, station in (("f3", fixture["origin_code"].lower()), ("f4", fixture["destination_code"])):
                await pilot.press(key)
                await until(pilot, lambda: isinstance(app.screen, StationScreen), "station picker")
                app.screen.query_one(Input).value = station
                await pilot.press("enter")
                await until(pilot, lambda: not app.busy, "station selection")
            app.query_one("#date", Input).value = fixture["date"]
            app.action_do("documents")
            await until(pilot, lambda: isinstance(app.screen, FormScreen), "document search")
            app.screen.query_one("#type", Input).value = doc["document_type"]
            app.screen.query_one("#country", Input).value = doc["issuing_country"]
            app.screen.query_one("#number", Input).value = doc["document_number"]
            await pilot.press("f8")
            await until(pilot, lambda: isinstance(app.screen, MessageScreen), "document selection")
            await pilot.click("#yes")
            await until(pilot, lambda: not app.busy, "document confirmed")
            assert app.document_id == str(saved["id"])
            checks.append("actual TUI selects real passenger document")
            await pilot.press("f12")
            await until(pilot, lambda: not app.busy, "real journey search")
            row = next(i for i, j in enumerate(app.journeys) if int(j["id"]) == fixture["trip_id"])
            app.query_one("#journeys", DataTable).move_cursor(row=row)
            app.query_one("#journeys", DataTable).focus()
            await pilot.press("enter")
            await until(pilot, lambda: not app.busy, "durable draft")
            assert len(app.drafts) == 1
            draft = app.outbox.drafts(app.scope)[0]
            assert draft["payload"]["origin"] == fixture["origin_code"]
            assert draft["payload"]["destination"] == fixture["destination_code"]
            await pilot.press("alt+n")
            await until(pilot, lambda: isinstance(app.screen, MessageScreen), "issue confirmation")
            await pilot.click("#yes")
            await until(pilot, lambda: isinstance(app.screen, ReceiptScreen), "actual ticket issue")
            order = app.outbox.list(app.scope)[0]
            ticket = order["ticket"]
            assert ticket["status"] == "OPEN"
            assert ticket["coupons"][0]["origin"]["station"]["telegraph_code"] == fixture["origin_code"]
            assert ticket["passenger_document_id"] == saved["id"]
            assert int(ticket["amount_minor"]) == int(before["amount_minor"])
            checks.append("actual TUI issues real PHP ticket with document and fare version")
            await pilot.press("escape")
            await until(pilot, lambda: not app.busy, "receipt close")
            again = (
                await client.request(
                    "POST", "/api/v1/tickets", payload=order["payload"], idempotency_key=order["id"]
                )
            )["data"]
            assert again["ticket_number"] == ticket["ticket_number"]
            assert int((await quote())["available"]) == 9
            checks.append("same-key retry returns same ticket and consumes inventory once")
            fetched = (await client.request("GET", "/api/v1/tickets/" + ticket["ticket_number"]))["data"]
            assert fetched["status"] == "OPEN"
            checks.append("real signed ticket lookup")
            app.query_one("#queue", DataTable).focus()
            await pilot.press("enter")
            await until(pilot, lambda: isinstance(app.screen, ChoiceScreen), "TUI ticket lookup")
            await pilot.press("down", "enter")
            await until(pilot, lambda: isinstance(app.screen, MessageScreen), "refund confirmation")
            await pilot.click("#yes")
            await until(pilot, lambda: isinstance(app.screen, ReceiptScreen), "actual refund")
            assert app.outbox.get(order["id"])["ticket"]["status"] == "RFND"
            checks.append("actual TUI refunds ticket against real PHP API")
            await pilot.press("escape")
            await until(pilot, lambda: not app.busy, "refund receipt close")
            refunded = (
                await client.request("POST", "/api/v1/tickets/" + ticket["ticket_number"] + "/refund")
            )["data"]
            assert refunded["status"] == "RFND"
            assert int((await quote())["available"]) == 10
            checks.append("refund restores inventory; repeated refund does not over-credit")
    finally:
        await client.close()


async def main():
    suffix = secrets.token_hex(5).upper()
    data = root / ".local" / ("live-" + suffix)
    data.mkdir(parents=True)
    checks = []
    server = None
    setup_attempted = False
    report = {"checks": checks, "cleanup_complete": False}
    try:
        setup_attempted = True
        fixture = await asyncio.to_thread(php_fixture, "setup", suffix)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with (data / "php-server.log").open("w", encoding="utf-8") as log:
            server = await asyncio.to_thread(
                subprocess.Popen,
                ["php", "-S", f"127.0.0.1:{port}", "-t", "public", "public/router.php"],
                cwd=backend,
                stdout=log,
                stderr=log,
            )
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient(timeout=2) as health:
                for _ in range(50):
                    try:
                        response = await health.get(base + "/health")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(0.1)
                else:
                    raise RuntimeError("Temporary PHP backend did not start")
            await exercise(base, fixture, data, checks)
    finally:
        try:
            if setup_attempted:
                await asyncio.to_thread(php_fixture, "cleanup", suffix)
                verified = await asyncio.to_thread(
                    subprocess.run,
                    ["php", str(root / "tools" / "verify_fixture_cleanup.php"), suffix],
                    cwd=backend,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                report["remaining_fixture_rows"] = json.loads(verified.stdout)
                report["cleanup_complete"] = True
        finally:
            if server:
                server.terminate()
                try:
                    await asyncio.to_thread(server.wait, timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    await asyncio.to_thread(server.wait)
            report["passed"] = len(checks) == 11 and report["cleanup_complete"]
            (data / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for check in checks:
                print("PASS", check)
            print("CLEANUP", report["cleanup_complete"])
            print("REPORT", data / "report.json")
    assert report["passed"], "Live backend verification incomplete"


if __name__ == "__main__":
    asyncio.run(main())
