import asyncio

import pytest
from textual.widgets import DataTable, Input

from ttrs.app import TicketApp
from ttrs.config import Config
from ttrs.screens import ChoiceScreen, FormScreen, MessageScreen, StationScreen


async def ready(app, pilot):
    for _ in range(120):
        await pilot.pause(0.01)
        if not app.busy:
            return
    raise AssertionError("UI worker did not finish")


@pytest.mark.parametrize("ascii_mode", [False, True])
async def test_keyboard_sale_query_and_refund(tmp_path, ascii_mode):
    app = TicketApp(Config(ascii=ascii_mode), demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        assert app.client is not None
        await pilot.press("f12")
        await ready(app, pilot)
        assert app.query_one("#journeys", DataTable).row_count == 2
        await pilot.press("enter")
        await ready(app, pilot)
        assert len(app.drafts) == 1
        assert app.query_one("#queue", DataTable).row_count == 1
        await pilot.press("alt+n")
        await pilot.pause()
        assert isinstance(app.screen, MessageScreen)
        await pilot.click("#yes")
        await pilot.pause()
        assert isinstance(app.screen, MessageScreen)
        assert len(app.server.tickets) == 1
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.outbox.list(app.scope)[0]["state"] == "issued"
        # Enter opens a live lookup of the selected ticket.
        app.query_one("#queue", DataTable).focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        await pilot.press("down", "enter")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert next(iter(app.server.tickets.values()))["status"] == "RFND"
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.outbox.list(app.scope)[0]["ticket"]["status"] == "RFND"
        if ascii_mode:
            assert app.query_one("#journey-panel").styles.border_top[0] == "ascii"


async def test_station_picker_modal_keys_and_cancel(tmp_path):
    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        await pilot.press("f3")
        await pilot.pause()
        assert isinstance(app.screen, StationScreen)
        await pilot.press("z", "z", "enter")
        await ready(app, pilot)
        assert app.origin_station["name"] == "郑州"
        await pilot.press("f1")
        assert app.focused.id == "date"
        await pilot.press("f5")
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, FormScreen)
        await pilot.press("f1")
        assert app.focused.id == "name"  # F1 must stay inside the modal.
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.passenger_name == "演示旅客"


async def test_query_change_discards_inflight_result(tmp_path):
    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        original = app.client.request
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed(method, path, **kwargs):
            if path.endswith("/journeys"):
                started.set()
                await release.wait()
            return await original(method, path, **kwargs)

        app.client.request = delayed
        await pilot.press("f12")
        await started.wait()
        app.query_one("#train", Input).value = "G101"
        release.set()
        await ready(app, pilot)
        assert app.journeys == []
        assert app.query_one("#journeys", DataTable).row_count == 0


async def test_existing_and_new_document_selection(tmp_path):
    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        await pilot.click("#documents")
        await pilot.pause()
        app.screen.query_one("#number", Input).value = "DEMO0001"
        await pilot.press("f8")
        await pilot.pause()
        await pilot.click("#yes")
        await ready(app, pilot)
        assert app.document_id == "1"
        await pilot.click("#documents")
        await pilot.pause()
        app.screen.query_one("#number", Input).value = "DEMO0002"
        await pilot.press("f8")
        await pilot.pause()
        assert isinstance(app.screen, FormScreen)
        app.screen.query_one("#given", Input).value = "新旅客"
        app.screen.query_one("#birth", Input).value = "19900101"
        await pilot.press("f8")
        await ready(app, pilot)
        assert app.document_id == "2"
        await pilot.press("f12")
        await ready(app, pilot)
        await pilot.press("enter")
        await ready(app, pilot)
        assert app.drafts[0]["payload"]["document_id"] == 2
        assert "passenger" not in app.drafts[0]["payload"]


@pytest.mark.parametrize("size", [(100, 30), (80, 24)])
async def test_menu_custom_alias_and_smaller_screen(tmp_path, size):
    app = TicketApp(Config(keys={"search": "ctrl+r"}), demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=size) as pilot:
        await ready(app, pilot)
        assert app.query_one("#destination").region.right <= size[0]
        assert app.query_one("#actions").region.bottom <= size[1]
        await pilot.press("ctrl+r")
        await ready(app, pilot)
        assert len(app.journeys) == 2
        await pilot.press("f10")
        await pilot.pause()
        assert isinstance(app.screen, ChoiceScreen)
        await pilot.press("escape")
        await ready(app, pilot)
        await pilot.press("f3")
        await pilot.pause()
        app.screen.query_one(Input).value = "[DEMO]"  # Untrusted content must be plain text.
        await pilot.pause()
        assert app.screen.query_one(DataTable).row_count == 0
        await pilot.press("escape")
        await ready(app, pilot)


@pytest.mark.parametrize("mode_key", ["ctrl+y", "ctrl+l"])
async def test_continuous_entry_locks_origin_and_filters_next_departure(tmp_path, mode_key):
    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        await pilot.press(mode_key, "f12")
        await ready(app, pilot)
        await pilot.press("enter")
        await ready(app, pilot)
        assert len(app.drafts) == 1
        assert app.query_one("#journeys", DataTable).row_count == 0
        assert "2 条" not in app.query_one("#journey-panel").border_title
        assert app.origin_station["name"] == "南京"
        assert app.flow.earliest.strftime("%H:%M") == "11:20"
        if mode_key == "ctrl+l":
            assert app.destination_station is None
            await pilot.press("f3")
            await pilot.pause()
            assert isinstance(app.screen, MessageScreen)
            assert "上一程" in app.screen.text
            await pilot.press("escape")
            await ready(app, pilot)
            await pilot.press("f4")
            await pilot.pause()
            await pilot.press("z", "z", "enter")
            await ready(app, pilot)
        else:
            assert app.destination_station["name"] == "西安"
        await pilot.press("f12")
        await ready(app, pilot)
        assert len(app.journeys) == 1
        assert app.journeys[0]["train_number"] == "G303"
        await pilot.press("enter")
        await ready(app, pilot)
        assert len(app.drafts) == 2
        assert app.drafts[0]["passenger"] == app.drafts[1]["passenger"]
        assert app.flow.mode == ("normal" if mode_key == "ctrl+y" else "connection")


async def test_edit_draft_rejection_keeps_focus_and_original_key(tmp_path):
    from ttrs.client import APIError

    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        await pilot.press("f12")
        await ready(app, pilot)
        await pilot.press("enter")
        await ready(app, pilot)
        await pilot.press("alt+m")
        await pilot.pause()
        app.screen.query_one("#name", Input).value = "  修改旅客  "
        await pilot.press("f8")
        await ready(app, pilot)
        assert app.drafts[0]["payload"]["passenger"] == "修改旅客"
        # Add a second draft; failure of the first must not move selection onto it.
        app.query_one("#journeys", DataTable).focus()
        await pilot.press("enter")
        await ready(app, pilot)
        app.query_one("#queue", DataTable).move_cursor(row=0)
        original = app.client.request
        attempts = []

        async def refuse_once(method, path, **kwargs):
            if path == "/api/v1/tickets":
                attempts.append(kwargs)
                if len(attempts) == 1:
                    raise APIError(409, "票价版本发生变化")
            return await original(method, path, **kwargs)

        app.client.request = refuse_once
        await pilot.press("alt+n")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert isinstance(app.screen, MessageScreen)
        assert len(app.drafts) == 1
        selected = app.selected_order()
        assert selected["state"] == "blocked"
        assert "票价版本" in selected["last_error"]
        key = selected["id"]
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.selected_order()["id"] == key
        await pilot.press("alt+m")
        await pilot.pause()
        assert isinstance(app.screen, MessageScreen)
        assert "仅未提交" in app.screen.text
        await pilot.press("escape")
        await ready(app, pilot)
        await pilot.press("alt+n")
        await pilot.pause()
        assert "票价版本" in app.screen.text
        await pilot.click("#yes")
        await pilot.pause()
        assert len(app.server.tickets) == 1
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.selected_order()["id"] == key
        assert app.selected_order()["state"] == "issued"
        assert attempts[0]["idempotency_key"] == attempts[1]["idempotency_key"]
        assert attempts[0]["payload"] == attempts[1]["payload"]
        assert len(app.drafts) == 1


async def test_persisted_draft_recovered_edited_and_submitted(tmp_path):
    path = tmp_path / "state.db"
    app = TicketApp(demo=True, store_path=path)
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        await pilot.press("f12")
        await ready(app, pilot)
        await pilot.press("enter")
        await ready(app, pilot)
        draft_id = app.drafts[0]["id"]
    # Closing without an issue POST must retain the draft.
    app = TicketApp(demo=True, store_path=path)
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        assert app.drafts[0]["id"] == draft_id
        app.query_one("#queue", DataTable).focus()
        await pilot.press("alt+m")
        await pilot.pause()
        app.screen.query_one("#name", Input).value = "恢复后的旅客"
        await pilot.press("f8")
        await ready(app, pilot)
        assert app.outbox.drafts(app.scope)[0]["passenger"] == "恢复后的旅客"
        await pilot.press("alt+n")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert "恢复后的旅客" in app.screen.text
        assert len(app.server.tickets) == 1
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.outbox.drafts(app.scope) == []
        assert len(app.outbox.list(app.scope)) == 1


@pytest.mark.parametrize("size", [(120, 36), (80, 24)])
async def test_readable_ticket_raw_view_and_explicit_export(tmp_path, monkeypatch, size):
    from ttrs.screens import ReceiptScreen

    monkeypatch.setenv("TTRS_STATE_DIR", str(tmp_path / "exports"))
    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=size) as pilot:
        await ready(app, pilot)
        await pilot.press("f12")
        await ready(app, pilot)
        await pilot.press("enter")
        await ready(app, pilot)
        await pilot.press("alt+n")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        assert isinstance(app.screen, ReceiptScreen)
        assert app.screen.query_one("#export").region.bottom <= size[1]
        assert app.screen.query_one("#back").region.right <= size[0]
        assert "西安 → 南京" in app.screen.text
        assert "120.00 CNY" in app.screen.text
        assert not (tmp_path / "receipt.txt").exists()
        await pilot.press("f7")
        await pilot.pause()
        assert app.screen.heading == "原始客票数据"
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ReceiptScreen)
        await pilot.press("f8")
        await pilot.pause()
        assert isinstance(app.screen, FormScreen)
        target = tmp_path / "receipt.txt"
        app.screen.query_one("#path", Input).value = str(target)
        await pilot.press("f8")
        await pilot.pause()
        assert target.exists()
        assert app.screen.heading == "已导出"
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("escape")
        await ready(app, pilot)


async def test_live_runtime_footer_counts_actions_and_tracks_ticket(tmp_path):
    from textual.widgets import Static

    app = TicketApp(demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(80, 24)) as pilot:
        await ready(app, pilot)
        status = app.query_one("#status", Static)
        before = str(status.content)
        assert "演示" not in before and "测试" not in before
        assert app.operation_count == 0
        assert status.region.bottom <= 24
        await pilot.pause(1.1)
        after = str(status.content)
        assert before.split(" |")[0] != after.split(" |")[0]
        assert "客户端CPU —" not in after
        await pilot.press("f12")
        await ready(app, pilot)
        assert app.operation_count == 1
        await pilot.press("enter")
        await ready(app, pilot)
        assert app.operation_count == 2
        assert "本张票号 待生成" in str(status.content)
        await pilot.press("alt+n")
        await pilot.pause()
        await pilot.click("#yes")
        await pilot.pause()
        number = next(iter(app.server.tickets))
        assert number in str(status.content)
        await pilot.press("escape")
        await ready(app, pilot)
        assert app.operation_count == 3
        app.probe_server()
        await pilot.pause()
        assert app.operation_count == 3


@pytest.mark.parametrize("size", [(120, 36), (80, 24)])
async def test_top_menu_shortcuts_and_configured_window_title(tmp_path, size):
    from rich.cells import cell_len
    from textual.widgets import Static

    app = TicketApp(Config(version="9.8.7", ascii=True), demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=size) as pilot:
        await ready(app, pilot)
        assert app.title == (
            "氢气工艺服务器交通信息单一窗口 HydCraft Server Transit Information Single Windows tTRS | 9.8.7"
        )
        assert "9.8.7" in str(app.query_one("#identity", Static).content)
        assert (
            "Ctrl+Q" in str(app.query_one("#quit").label)
            if size[0] >= 110
            else "^Q" in str(app.query_one("#quit").label)
        )
        for button in app.query("#menubar Button"):
            assert button.region.right <= size[0]
            assert cell_len(str(button.label)) <= button.content_region.width
        for key, expected in [
            ("f10", ChoiceScreen),
            ("f6", ChoiceScreen),
            ("ctrl+o", MessageScreen),
            ("ctrl+p", FormScreen),
            ("ctrl+g", FormScreen),
            ("f8", MessageScreen),
            ("ctrl+q", MessageScreen),
        ]:
            app.query_one("#date", Input).focus()
            await pilot.press(key)
            await pilot.pause()
            assert isinstance(app.screen, expected), key
            await pilot.press("escape")
            await ready(app, pilot)


async def test_configured_top_menu_alias_is_shown_and_works(tmp_path):
    app = TicketApp(Config(keys={"help": "f7"}), demo=True, store_path=tmp_path / "state.db")
    async with app.run_test(size=(120, 36)) as pilot:
        await ready(app, pilot)
        assert "F7" in str(app.query_one("#help").label)
        await pilot.press("f7")
        await pilot.pause()
        assert isinstance(app.screen, MessageScreen)
        await pilot.press("escape")
        await ready(app, pilot)
