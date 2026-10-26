"""Modal screens keep key handling local, including printable button mnemonics."""

from typing import ClassVar, NamedTuple

import httpx
from rich.text import Text
from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, ListItem, ListView, Static

from .auth import SignatureError
from .client import APIError, load_stations
from .domain import station_matches


class Field(NamedTuple):
    id: str
    label: str
    value: str = ""
    password: bool = False


class FormScreen(ModalScreen[dict | None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "返回", priority=True),
        Binding("f8", "submit", "确认", priority=True),
    ]

    def __init__(self, title: str, fields: list[Field], note: str = ""):
        super().__init__()
        self.heading, self.fields, self.note = title, fields, note
        if len(fields) >= 3:
            self.add_class("tall-form")

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            with VerticalScroll(classes="form-fields"):
                for i, field in enumerate(self.fields, 1):
                    yield Label(f"F{i}. {field.label}", markup=False)
                    yield Input(value=field.value, password=field.password, id=field.id)
                if self.note:
                    yield Static(self.note, markup=False)
            with Horizontal(classes="dialog-actions"):
                yield Button("[确认 F8]", id="submit", variant="primary")
                yield Button("[返回 Esc]", id="back")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_key(self, event: events.Key) -> None:
        for i, field in enumerate(self.fields, 1):
            if event.key == f"f{i}" and i <= 7:
                self.query_one("#" + field.id, Input).focus()
                event.stop()
                event.prevent_default()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        inputs = list(self.query(Input))
        index = inputs.index(event.input)
        if index + 1 < len(inputs):
            inputs[index + 1].focus()
        else:
            self.action_submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "submit":
            self.action_submit()
        else:
            self.action_cancel()

    def action_submit(self) -> None:
        self.dismiss({field.id: self.query_one("#" + field.id, Input).value for field in self.fields})

    def action_cancel(self) -> None:
        self.dismiss(None)


class MessageScreen(ModalScreen[bool]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "返回", priority=True)]

    def __init__(self, title: str, text: str, confirm: bool = False):
        super().__init__()
        self.heading, self.text, self.confirm = title, text, confirm
        if len(text) > 400 or text.count("\n") > 8:
            self.add_class("long-message")

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            with VerticalScroll(classes="message-body"):
                yield Static(self.text, markup=False)
            with Horizontal(classes="dialog-actions"):
                if self.confirm:
                    yield Button("[确认执行]", id="yes", variant="warning")
                yield Button("[返回 Esc]", id="back")

    def on_mount(self) -> None:
        self.query_one("#back", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class ChoiceScreen(ModalScreen[str | None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "返回", priority=True)]

    def __init__(self, title: str, choices: list[tuple[str, str]]):
        super().__init__()
        self.heading, self.choices = title, choices

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            yield ListView(*(ListItem(Label(label, markup=False)) for _, label in self.choices), id="choices")
            yield Button("[返回 Esc]", id="back")

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = self.query_one(ListView).index
        self.dismiss(self.choices[index][0] if index is not None else None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class StationScreen(ModalScreen[dict | None]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "返回", priority=True)]

    def __init__(self, title: str, stations: list[dict], client):
        super().__init__()
        self.heading, self.stations, self.client = title, list(stations), client
        self.filtered: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            yield Input(placeholder="电报码 / 中文名 / 英文名 / 拼音 / 站 ID", id="station-filter")
            yield Static("仅显示可见车站；支持电报码和拼音检索，服务器查询会刷新全部匹配页。", markup=False)
            yield DataTable(id="station-results", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="dialog-actions"):
                yield Button("[选择]", id="choose", variant="primary")
                yield Button("[服务器查询]", id="remote")
                yield Button("[返回 Esc]", id="back")

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns("电报码", "中文站名", "英文站名", "归属企业", "行政区", "维度")
        self.filter("")
        self.query_one(Input).focus()

    def filter(self, query: str) -> None:
        self.filtered = [s for s in self.stations if station_matches(s, query)]
        table = self.query_one(DataTable)
        table.clear()
        for i, station in enumerate(self.filtered):
            table.add_row(
                Text(str(station.get("telegraph_code") or "—")),
                Text(str(station.get("name_zh") or station["name"])),
                Text(str(station.get("name_en") or "—")),
                Text(str(station.get("operator_code") or "—")),
                Text(
                    " / ".join(str(station[k]) for k in ("admin_level_1", "admin_level_2") if station.get(k))
                ),
                Text(str(station.get("dimension", ""))),
                key=str(i),
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self.filter(event.value)

    def on_input_submitted(self) -> None:
        self.choose()

    def on_data_table_row_selected(self) -> None:
        self.choose()

    def choose(self) -> None:
        row = self.query_one(DataTable).cursor_row
        if 0 <= row < len(self.filtered):
            self.dismiss(self.filtered[row])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "choose":
            self.choose()
        elif event.button.id == "remote":
            self.remote_search()
        else:
            self.dismiss(None)

    @work(exclusive=True, group="station-search")
    async def remote_search(self) -> None:
        button = self.query_one("#remote", Button)
        query = self.query_one(Input).value.strip()
        button.disabled = True
        try:
            self.stations = await load_stations(self.client, query)
            self.filter(self.query_one(Input).value)
        except (APIError, SignatureError, httpx.HTTPError, ValueError, KeyError) as exc:
            self.notify(str(exc), severity="error")
        finally:
            button.disabled = False

    def action_cancel(self) -> None:
        self.dismiss(None)


class ReceiptScreen(MessageScreen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "返回", priority=True),
        Binding("f8", "export", "导出", priority=True),
        Binding("f7", "raw", "原始数据", priority=True),
    ]

    def __init__(self, ticket: dict, stations: dict[str, str], *, ascii_mode: bool = False):
        super().__init__("电子客票 · " + str(ticket["ticket_number"]), "")
        self.ticket, self.stations, self.ascii_mode = ticket, stations, ascii_mode
        self.choice: str | None = None
        self.add_class("receipt-dialog")

    def compose(self) -> ComposeResult:
        from .receipt import format_receipt

        self.text = format_receipt(
            self.ticket,
            self.stations,
            width=min(64, max(24, self.app.size.width - 24)),
            ascii_mode=self.ascii_mode,
        )
        with Vertical(id="dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            with VerticalScroll(classes="message-body"):
                yield Static(self.text, markup=False)
            with Horizontal(classes="dialog-actions"):
                yield Button("[导出 F8]", id="export", variant="primary")
                yield Button("[原始数据 F7]", id="raw")
                yield Button("[返回 Esc]", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "export":
            self.action_export()
        elif event.button.id == "raw":
            self.action_raw()
        else:
            self.dismiss(False)

    def action_export(self) -> None:
        self.choice = "export"
        self.dismiss(False)

    def action_raw(self) -> None:
        self.choice = "raw"
        self.dismiss(False)
