"""Full-screen ticket desk. Business operations run in one serialized worker."""

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import ClassVar

import httpx
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static

from . import APP_TITLE
from .auth import SignatureError
from .client import APIError, TicketClient
from .config import Config, state_path
from .demo import DEMO_KEY, STATIONS, DemoServer
from .domain import money, parse_date, parse_travel_date, sale_payload, today
from .flow import JourneyFlow
from .receipt import export_name, export_ticket
from .runtime import ProcessMonitor, format_status
from .screens import ChoiceScreen, Field, FormScreen, MessageScreen, ReceiptScreen, StationScreen
from .store import Outbox

HELP = """tTRS 0.4 操作说明

F1 日期（UTC） / F2 车次 / F3 发站 / F4 到站 / F5 旅客
F9 切换余票与待办表格；方向键选择，Enter 取入待办或查看订单
F12 查余票 / Alt+R 取入待办 / Alt+N 出票 / Alt+E 取消未提交待办
Ctrl+O 连接 / Ctrl+G 查票与退票 / Ctrl+F12 逐站时刻 / F10 菜单
Ctrl+Q 或 Ctrl+C 退出；Alt+S、Alt+D 返回售票录入
表单：F1–F7 定位字段，Enter 下一项，F8 提交，Esc 返回
所有操作也有可用 Tab 定位的按钮或菜单入口。
F6 业务模式；Ctrl+Y 往返；Ctrl+L 联程；Alt+S 普通售票；Alt+M 修改未提交旅客。
日期支持 YYYYMMDD、YYYY-MM-DD、日简码（如 30）和 +N 天（如 +1）。
往返自动交换站点，联程锁定上一程到站为下一程发站；日期和时刻按 UTC 衔接。
连续录入生成独立客票，没有通票票价、联程保障或整体原子出票。

部分终端会拦截或合并组合键；F11 在 Windows Terminal 默认是全屏。
Ctrl+3/4、Ctrl+H 不作为业务入口。使用 --keys 诊断、--config 修改键位。

待办不锁库存、报价不锁定，出票以后端校验为准。每条订单单独提交。
网络错误或验签失败后保留“待确认”订单，用原记录同键重试。
已验签的后端拒绝保留原因，重试仍使用原订单。拒绝不等同于已成功退票。
已提交订单不可直接删除或修改。重启后连接相同服务和身份可以恢复。
未提交待办自动保存在本地；退出、切换出票方后重新连接即可恢复。
本地订单库含旅客和客票数据，不保存 API 密钥，请按业务数据保护。
票面 F7 查看原始数据、F8 导出 TXT/JSON；TXT 默认遮蔽证件号码。

支持：车站和拼音检索、区间余票与报价、逐站时刻、证件查询与登记、
姓名或证件出票、持久化幂等恢复、查票、整票退票。
后端暂未提供：席位分配、折扣、用途票额、付款、改签、通票签证、
纸票打印和交班结算。这些功能不会显示为可办理。
业务日期与列车时刻保持后端 UTC；底部运行时钟跟随本地时区。
运行面板：本张/下一张票号、会话操作次数、网络、HTTP 往返和已验签服务处理耗时。
CPU 与 RSS 为当前客户端进程；后台健康探测不计操作次数。下一张票号在出票时随机生成。
"""
MENU = [
    ("normal_sale", "普通售票 / Alt+S"),
    ("roundtrip", "往返连续录入 / Ctrl+Y"),
    ("connection", "联程连续录入 / Ctrl+L"),
    ("edit_row", "修改未提交待办旅客 / Alt+M"),
    ("search", "查询余票 / F12"),
    ("take", "取入待办 / Alt+R"),
    ("issue", "出票或确认原订单 / Alt+N"),
    ("cancel_row", "取消未提交待办 / Alt+E"),
    ("details", "逐站时刻 / Ctrl+F12"),
    ("passenger", "旅客 / F5"),
    ("documents", "证件库：查询或登记"),
    ("ticket", "查票与退票 / Ctrl+G"),
    ("connect", "连接 / 切换出票方 / Ctrl+O"),
    ("help", "快捷键与能力说明"),
    ("quit", "退出 / Ctrl+Q"),
]
DEFAULT_KEYS = {
    "normal_sale": "alt+s,alt+d",
    "roundtrip": "ctrl+y",
    "connection": "ctrl+l",
    "mode": "f6",
    "edit_row": "alt+m",
    "focus_date": "f1",
    "focus_train": "f2",
    "origin": "f3",
    "destination": "f4",
    "passenger": "f5",
    "select_row": "f9",
    "menu": "f10",
    "search": "f12",
    "take": "alt+r",
    "issue": "alt+n",
    "cancel_row": "alt+e",
    "ticket": "ctrl+g",
    "connect": "ctrl+o",
    "details": "ctrl+f12",
    "quit": "ctrl+q,ctrl+c",
}


class TicketApp(App):
    TITLE = APP_TITLE
    CSS_PATH = "desk.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS: ClassVar[list[Binding]] = [
        Binding(key, f"do('{action}')", show=False) for action, key in DEFAULT_KEYS.items()
    ]

    def __init__(self, config: Config | None = None, *, demo=False, store_path: Path | None = None):
        super().__init__()
        self.config, self.demo = config or Config(), demo
        self.client: TicketClient | None = None
        self.server = DemoServer() if demo else None
        self.outbox = Outbox(store_path or state_path(demo))
        self.scope = ""
        self.flow = JourneyFlow()
        self.stations: list[dict] = []
        self.origin_station: dict | None = None
        self.destination_station: dict | None = None
        self.passenger_name, self.document_id = "", ""
        self.journeys: list[dict] = []
        self.drafts: list[dict] = []
        self.queue: list[dict] = []
        self.busy = False
        self.query_context: tuple | None = None
        self.query_number = 0
        self.monitor = ProcessMonitor()
        self.operation_count = 0
        self.visible_ticket_number = None
        self.last_ticket_number = None
        self.last_message = "未连接"
        self._closing = False
        self.runtime_timer = self.probe_timer = None

    def compose(self) -> ComposeResult:
        yield Static(APP_TITLE + "\n未连接 · Ctrl+O 连接后端", id="identity", markup=False)
        with Horizontal(id="menubar"):
            for ident, label in [
                ("menu", "菜单"),
                ("mode", "业务"),
                ("connect", "连接"),
                ("documents", "证件库"),
                ("ticket", "查票/退票"),
                ("help", "帮助"),
                ("quit", "退出"),
            ]:
                yield Button(f"[{label}]", id=ident)
        yield Static("普通售票 · F6 业务模式", id="mode-status", markup=False)
        with Horizontal(id="fields"):
            with Vertical(classes="date-field"):
                yield Static("F1. 日期 UTC", markup=False)
                yield Input(today(), id="date")
            with Vertical(classes="train-field"):
                yield Static("F2. 车次（可空）", markup=False)
                yield Input(placeholder="G101", id="train")
            for ident, label in [
                ("origin", "F3. 发站"),
                ("destination", "F4. 到站"),
                ("passenger", "F5. 旅客"),
            ]:
                with Vertical(classes="station-field"):
                    yield Static(label, markup=False)
                    yield Button("[选择]", id=ident)
        with Vertical(id="journey-panel"):
            yield DataTable(id="journeys", cursor_type="row", zebra_stripes=True)
        with Vertical(id="queue-panel"):
            yield DataTable(id="queue", cursor_type="row", zebra_stripes=True)
        yield Static("待办不锁库存；金额为查询报价。", id="totals", markup=False)
        with Horizontal(id="actions"):
            for ident, label in [
                ("search", "余票"),
                ("take", "取入待办"),
                ("issue", "出票"),
                ("cancel_row", "取消待办"),
                ("edit_row", "修改旅客"),
                ("details", "逐站时刻"),
            ]:
                yield Button(f"[{label}]", id=ident, variant="primary" if ident == "search" else "default")
        yield Static("", id="key-hints", markup=False)
        yield Static("", id="status", markup=False)

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        for action, keys in self.config.keys.items():
            if action not in DEFAULT_KEYS and action not in {item[0] for item in MENU}:
                raise ValueError(f"未知键位动作：{action}")
            # Default key still works as an alias; the configured key is the preferred display.
            self.bind(keys, f"do('{action}')", show=False)
        self.query_one("#journeys", DataTable).add_columns(
            "序", "车次 / 班次ID", "发站 → 到站", "出发 UTC", "到达 UTC", "余票", "区间报价"
        )
        self.query_one("#queue", DataTable).add_columns(
            "序", "车次 / 区间", "旅客", "报价/票价", "状态", "票号"
        )
        self.query_one("#journey-panel").border_title = "余票查询"
        self.query_one("#queue-panel").border_title = "待办 / 本地出票记录（F9 切换）"
        self.apply_borders()
        hints = "F1–F5 字段 | F6 业务 | F9 选票 | F10 菜单 | F12 余票 | Alt+R 取票 | Alt+N 出票"
        if self.config.keys:
            hints = "自定义键位 | " + " | ".join(f"{a}:{k}" for a, k in self.config.keys.items())
        self.query_one("#key-hints", Static).update(hints)
        self.query_one("#date", Input).focus()
        self.runtime_timer = self.set_interval(1, self.refresh_runtime)
        self.probe_timer = self.set_interval(10, self.probe_server)
        self.refresh_runtime()
        if self.demo:
            self.execute("demo_connect")

    def on_resize(self, event) -> None:
        if self.screen_stack:
            self.screen_stack[0].set_class(event.size.width < 110 or event.size.height < 34, "compact")

    def apply_borders(self) -> None:
        if self.config.ascii:
            self.screen.add_class("ascii")

    async def on_unmount(self) -> None:
        self._closing = True
        if self.runtime_timer:
            self.runtime_timer.stop()
        if self.probe_timer:
            self.probe_timer.stop()
        if self.client:
            await self.client.close()
        self.outbox.close()

    def status(self, text: str) -> None:
        self.last_message = text
        self.refresh_runtime()

    def current_ticket_number(self) -> str:
        if self.visible_ticket_number:
            return self.visible_ticket_number
        row = self.query_one("#queue", DataTable).cursor_row
        if 0 <= row < len(self.queue):
            order = self.queue[row]
            if order.get("ticket"):
                return str(order["ticket"]["ticket_number"])
            return "待生成" if order["state"] == "draft" else "待确认"
        return self.last_ticket_number or "—"

    def refresh_runtime(self) -> None:
        if not self.is_mounted or self._closing:
            return
        metrics = self.client.metrics if self.client else None
        self.query_one("#status", Static).update(
            format_status(
                self.monitor.sample(),
                metrics,
                self.current_ticket_number(),
                self.operation_count,
                local=self.demo and self.client is not None,
            )
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "queue":
            self.refresh_runtime()

    @work(group="heartbeat", exclusive=True)
    async def probe_server(self) -> None:
        client = self.client
        if client is not None and not self.demo and not self._closing:
            await client.probe()
            self.refresh_runtime()

    def record_operation(self) -> None:
        self.operation_count += 1
        self.refresh_runtime()

    async def modal(self, screen):
        # Apply the same border style before a modal is rendered.
        if self.config.ascii:
            screen.add_class("ascii")
        return await self.push_screen_wait(screen)

    def action_do(self, action: str) -> None:
        if len(self.screen_stack) != 1:
            return
        if action in {"focus_date", "focus_train"}:
            self.query_one("#date" if action == "focus_date" else "#train", Input).focus()
        elif action == "select_row":
            target = "#journeys" if self.focused is self.query_one("#queue") else "#queue"
            self.query_one(target, DataTable).focus()
        elif self.busy:
            self.notify("请先完成当前操作", severity="warning")
        else:
            self.execute(action)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id:
            self.action_do(event.button.id)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"date", "train"} and self.query_context is not None:
            self.clear_journeys()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "date":
            self.action_do("focus_train")
        elif event.input.id == "train":
            self.action_do("search")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_do("take" if event.data_table.id == "journeys" else "queue_open")

    @work(group="operations")
    async def execute(self, action: str) -> None:
        if self.busy:
            return
        self.busy = True
        self.status("处理中…")
        try:
            if action == "menu":
                selected = await self.modal(ChoiceScreen("业务菜单", MENU))
                if selected:
                    self.record_operation()
                    await self.handle(selected)
            else:
                if action != "demo_connect":
                    self.record_operation()
                await self.handle(action)
            if self.is_running:
                self.status("就绪")
        except (
            APIError,
            SignatureError,
            httpx.HTTPError,
            ValueError,
            KeyError,
            OSError,
            sqlite3.Error,
        ) as exc:
            self.refresh_queue()
            self.status("操作未完成：" + str(exc))
            await self.modal(
                MessageScreen(
                    "操作提示",
                    str(exc) + "\n\n已提交订单保留原单及错误详情；网络异常时同键重试，不要另建重复订单。",
                )
            )
        finally:
            self.busy = False

    async def handle(self, action: str) -> None:
        if action == "help":
            await self.modal(MessageScreen("操作说明", HELP))
        elif action == "quit":
            if await self.modal(
                MessageScreen(
                    "退出 tTRS",
                    "待办及已提交订单已保存在本地，可在下次连接相同服务和出票方后恢复；演示模式退出即清空。",
                    True,
                )
            ):
                self.exit()
        elif action in {"connect", "demo_connect"}:
            await self.connect(action == "demo_connect")
        elif action == "mode":
            selected = await self.modal(ChoiceScreen("选择业务模式", MENU[:3]))
            if selected:
                self.set_mode(selected)
        elif action in {"normal_sale", "roundtrip", "connection"}:
            self.set_mode(action)
        elif action == "passenger":
            await self.passenger()
        else:
            if not self.client:
                raise ValueError("请先通过连接按钮或 Ctrl+O 连接；也可使用 --demo 本地演示")
            if action in {"origin", "destination"}:
                await self.station(action)
            elif action == "search":
                await self.search()
            elif action == "take":
                await self.take()
            elif action == "issue":
                await self.issue()
            elif action == "cancel_row":
                self.cancel_row()
            elif action == "edit_row":
                await self.edit_row()
            elif action == "queue_open":
                row = self.selected_order()
                if row.get("ticket"):
                    await self.ticket(row["ticket"]["ticket_number"])
                else:
                    await self.issue()
            elif action == "details":
                await self.details()
            elif action == "documents":
                await self.documents()
            elif action == "ticket":
                await self.ticket()

    def set_mode(self, action: str) -> None:
        self.flow.reset("normal" if action == "normal_sale" else action)
        self.clear_journeys()
        self.update_mode()
        self.query_one("#date", Input).focus()

    def update_mode(self) -> None:
        self.query_one("#mode-status", Static).update(self.flow.label + " · F6 切换")

    async def connect(self, automatic=False) -> None:
        if self.demo:
            if not automatic:
                await self.modal(MessageScreen("演示模式", "不连接外部服务，退出后不保留演示客票。"))
                return
            values = {"base": "http://demo.local", "key": DEMO_KEY, "agency": ""}
        else:
            values = await self.modal(
                FormScreen(
                    "连接售票后端",
                    [
                        Field(
                            "base", "服务地址", self.client.base_url if self.client else self.config.base_url
                        ),
                        Field(
                            "key",
                            "API 密钥（仅存内存）",
                            self.client.api_key if self.client else os.environ.get("TICKETING_API_KEY", ""),
                            True,
                        ),
                        Field("agency", "管理员代操作出票方（普通出票方留空）", self.config.agency_code),
                    ],
                    "使用后端分配的 API 密钥，不是售票员工号密码。",
                )
            )
            if values is None:
                return
        candidate = TicketClient(
            values["base"],
            values["key"],
            values["agency"],
            self.config.timeout,
            httpx.MockTransport(self.server.handle) if self.server else None,
        )
        try:
            identity = (await candidate.request("GET", "/api/v1/me"))["data"]
            if identity.get("role") not in {"admin", "agency"}:
                raise ValueError("运营方身份不能使用售票窗口，请使用出票方或管理员密钥")
            stations = (await candidate.request("GET", "/api/v1/stations"))["data"]
        except BaseException:
            await candidate.close()
            raise
        agency = identity.get("agency_code", values["agency"])
        scope = hashlib.sha256(
            json.dumps([candidate.base_url, agency], ensure_ascii=False).encode()
        ).hexdigest()
        if self.client:
            await self.client.close()
        self.client, self.stations = candidate, stations
        self.scope = scope
        self.visible_ticket_number = self.last_ticket_number = None
        self.flow.reset()
        self.update_mode()
        self.origin_station = self.destination_station = None
        self.clear_journeys()
        self.passenger_name, self.document_id = "", ""
        for ident in ("origin", "destination", "passenger"):
            self.query_one("#" + ident, Button).label = "[选择]"
        self.query_one("#identity", Static).update(
            f"{APP_TITLE}\n{'[本地演示]' if self.demo else '[已连接]'} "
            f"出票方 {agency} · {candidate.base_url} · UTC"
        )
        if self.demo:
            self.origin_station, self.destination_station = dict(STATIONS[0]), dict(STATIONS[2])
            self.query_one("#origin", Button).label = "西安"
            self.query_one("#destination", Button).label = "南京"
            self.passenger_name = "演示旅客"
            self.query_one("#passenger", Button).label = "演示旅客"
        self.refresh_queue()

    def clear_journeys(self) -> None:
        self.query_number += 1
        self.journeys = []
        self.query_context = None
        self.query_one("#journeys", DataTable).clear()
        self.query_one("#journey-panel").border_title = "余票查询 · 请按 F12 查询"

    def context(self) -> tuple:
        return (
            self.query_one("#date", Input).value,
            self.query_one("#train", Input).value,
            self.origin_station["id"] if self.origin_station else "",
            self.destination_station["id"] if self.destination_station else "",
        )

    async def station(self, which: str) -> None:
        if self.flow.earliest and (which == "origin" or self.flow.mode == "roundtrip"):
            raise ValueError("后续行程站点由上一程确定；需要自由修改时先按 Alt+S 切回普通售票")
        selected = await self.modal(
            StationScreen("选择发站" if which == "origin" else "选择到站", self.stations, self.client)
        )
        if selected is not None:
            if which == "origin":
                self.origin_station = selected
            else:
                self.destination_station = selected
            self.query_one("#" + which, Button).label = Text(str(selected["name"]))
            if not any(s["id"] == selected["id"] for s in self.stations):
                self.stations.append(selected)
            self.clear_journeys()

    async def search(self) -> None:
        if not self.origin_station or not self.destination_station:
            raise ValueError("请先选择发站和到站（F3 / F4）")
        if self.origin_station["id"] == self.destination_station["id"]:
            raise ValueError("发站与到站不能相同")
        date = parse_travel_date(self.query_one("#date", Input).value)
        train = self.query_one("#train", Input).value.strip().upper()
        if train and not re.fullmatch(r"[DGCS][0-9]{1,16}", train):
            raise ValueError("车次支持 D/G/C/S 开头加数字，也可以留空")
        self.clear_journeys()
        captured, generation = self.context(), self.query_number
        params = {
            "origin": self.origin_station["id"],
            "destination": self.destination_station["id"],
            "date": date,
        }
        params.update(self.flow.window(date))
        if train:
            params["train_number"] = train
        result = await self.client.request("GET", "/api/v1/journeys", params=params)
        if captured != self.context() or generation != self.query_number:
            self.notify("条件已变化，旧查询结果已丢弃，请重新查询", severity="warning")
            return
        self.journeys = [j for j in result["data"] if self.flow.accepts(j["departure_at"])]
        self.query_context = captured
        table = self.query_one("#journeys", DataTable)
        label = self.origin_station["name"] + " → " + self.destination_station["name"]
        for i, journey in enumerate(self.journeys):
            table.add_row(
                str(i + 1),
                Text(f"{journey.get('train_number') or '—'} / {journey['id']}"),
                Text(label),
                Text(str(journey["departure_at"])),
                Text(str(journey["arrival_at"])),
                str(journey["available"]),
                Text(money(journey.get("amount_minor"), journey.get("currency", "CNY"))),
                key=str(i),
            )
        self.query_one("#journey-panel").border_title = f"{date} UTC · {len(self.journeys)} 条（最多 200）"
        table.focus()
        if not self.journeys:
            self.notify("没有符合条件的区间；请确认 UTC 日期、站点和运行图是否已导入")

    def selected_journey(self) -> dict:
        if self.query_context != self.context():
            raise ValueError("查询条件已变化，请重新查询余票")
        row = self.query_one("#journeys", DataTable).cursor_row
        if not 0 <= row < len(self.journeys):
            raise ValueError("请先查询并选择车次")
        return self.journeys[row]

    async def passenger(self) -> None:
        selected = await self.modal(
            ChoiceScreen(
                "旅客信息",
                [
                    ("name", "仅姓名出票（后端兼容模式）"),
                    ("document", "从证件库查询或登记"),
                ],
            )
        )
        if selected == "document":
            if not self.client:
                raise ValueError("请先连接后端")
            await self.documents()
        elif selected == "name":
            result = await self.modal(
                FormScreen(
                    "输入旅客姓名",
                    [
                        Field("name", "姓名", self.passenger_name),
                    ],
                    "后端允许仅姓名出票，不代表已完成实名证件核验。",
                )
            )
            if result is not None:
                name = result["name"].strip()
                if not name or len(name) > 160 or any(ord(c) < 32 for c in name):
                    raise ValueError("姓名须为 1–160 字符，不能含控制字符")
                self.passenger_name, self.document_id = name, ""
                self.query_one("#passenger", Button).label = Text(name)

    async def documents(self) -> None:
        form = await self.modal(
            FormScreen(
                "证件库精确查询",
                [
                    Field("type", "证件类型", "ID_CARD"),
                    Field("country", "归属地三字母", "CHN"),
                    Field("number", "证件号码"),
                ],
                "按类型、归属地和号码精确查询；未登记时可补全资料创建。",
            )
        )
        if form is None:
            return
        params = {
            "document_type": form["type"].strip().upper(),
            "issuing_country": form["country"].strip().upper(),
            "document_number": form["number"].strip().upper(),
        }
        if (
            not params["document_type"]
            or not params["document_number"]
            or not re.fullmatch(r"[A-Z]{3}", params["issuing_country"])
        ):
            raise ValueError("请输入类型、证件号码和三字母归属地")
        found = (await self.client.request("GET", "/api/v1/passenger-documents", params=params))["data"]
        if found:
            document = found[0]
            if not await self.modal(
                MessageScreen(
                    "选择已有证件",
                    f"证件库 ID：{document['id']}\n姓名：{document['display_name']}\n"
                    f"类型：{document['document_type']}\n归属地：{document['issuing_country']}\n"
                    f"号码：{document['document_number']}\n版本：{document['version']}",
                    True,
                )
            ):
                return
        else:
            extra = await self.modal(
                FormScreen(
                    "登记新证件",
                    [
                        Field("given", "名 / 中文姓名"),
                        Field("surname", "姓（可空）"),
                        Field("birth", "出生日期 YYYY-MM-DD"),
                        Field("reason", "登记原因", "售票窗口首次登记"),
                    ],
                    "F8 提交新证件；资料必须与旅客证件一致。",
                )
            )
            if extra is None:
                return
            if not extra["given"].strip() or not extra["reason"].strip():
                raise ValueError("姓名和登记原因不能为空")
            payload = {
                **params,
                "given_name": extra["given"].strip(),
                "surname": extra["surname"].strip() or None,
                "birth_date": parse_date(extra["birth"]),
                "reason": extra["reason"].strip(),
            }
            try:
                document = (
                    await self.client.request("POST", "/api/v1/passenger-documents", payload=payload)
                )["data"]
            except APIError as exc:
                if exc.status != 409:
                    raise
                raise ValueError("证件已由其他窗口登记，请重新查询并核对资料后选择") from exc
        self.document_id, self.passenger_name = str(document["id"]), str(document["display_name"])
        self.query_one("#passenger", Button).label = Text(f"{self.passenger_name} [证件]")

    async def take(self) -> None:
        journey = dict(self.selected_journey())
        if not self.passenger_name and not self.document_id:
            await self.passenger()
        if not self.passenger_name and not self.document_id:
            return
        payload = sale_payload(journey, self.passenger_name, self.document_id)
        label = f"{journey.get('train_number') or journey['id']} " + (
            self.origin_station["name"] + " → " + self.destination_station["name"]
        )
        key = self.outbox.save_draft(self.scope, payload, label, self.passenger_name, journey)
        self.refresh_queue(key)
        self.query_one("#queue", DataTable).focus()
        next_stations = self.flow.advance(
            self.origin_station, self.destination_station, journey["arrival_at"]
        )
        if next_stations:
            self.origin_station, self.destination_station = next_stations
            self.query_one("#origin", Button).label = Text(str(self.origin_station["name"]))
            self.query_one("#destination", Button).label = (
                Text(str(self.destination_station["name"])) if self.destination_station else "[选择]"
            )
            self.query_one("#date", Input).value = self.flow.earliest.date().isoformat()
            self.query_one("#train", Input).value = ""
            self.clear_journeys()
            self.query_one("#date" if self.flow.mode == "roundtrip" else "#destination").focus()
        self.update_mode()

    def refresh_queue(self, focus_id: str | None = None) -> None:
        if not self.is_mounted:
            return
        table = self.query_one("#queue", DataTable)
        old = table.cursor_row
        previous_id = self.queue[old]["id"] if 0 <= old < len(self.queue) else None
        focus_id = focus_id or previous_id
        stored = self.outbox.list(self.scope) if self.scope else []
        self.drafts = self.outbox.drafts(self.scope) if self.scope else []
        self.queue = [*self.drafts, *stored]
        table.clear()
        totals: dict[str, int] = {}
        for i, row in enumerate(self.queue):
            ticket = row.get("ticket")
            if ticket:
                passenger, amount = ticket.get("passenger", ""), ticket.get("amount_minor")
                currency = ticket.get("currency", "CNY")
                state = "已退票" if ticket.get("status") == "RFND" else "已出票"
            elif row["state"] == "draft":
                passenger, amount = row["passenger"], row["journey"].get("amount_minor")
                currency = row["journey"].get("currency", "CNY")
                totals[currency] = totals.get(currency, 0) + int(amount or 0)
                state = "未提交"
            else:
                passenger = row["payload"].get("passenger", f"证件 #{row['payload'].get('document_id', '')}")
                amount, currency = None, "CNY"
                state = "后端拒绝 / 原单重试" if row["state"] == "blocked" else "待确认 / 同键重试"
            table.add_row(
                str(i + 1),
                Text(row["label"]),
                Text(str(passenger)),
                Text(money(amount, currency)),
                state,
                Text(str(ticket.get("ticket_number", ""))) if ticket else "",
                key=row["id"],
            )
        if self.queue:
            selected = next(
                (i for i, row in enumerate(self.queue) if row["id"] == focus_id),
                min(max(old, 0), len(self.queue) - 1),
            )
            table.move_cursor(row=selected)
        issued = sum(row["state"] == "issued" for row in stored)
        pending = sum(row["state"] == "pending" for row in stored)
        blocked = sum(row["state"] == "blocked" for row in stored)
        amount_text = " / ".join(money(v, c) for c, v in totals.items()) or "0.00"
        self.query_one("#totals", Static).update(
            f"待出票 {len(self.drafts)} 张 | 待确认 {pending} 张 | 拒绝 {blocked} 张 | 已处理 {issued} 张 | "
            f"待办报价 {amount_text} · 未锁库存 / 未收款"
        )

    def selected_order(self) -> dict:
        row = self.query_one("#queue", DataTable).cursor_row
        if not 0 <= row < len(self.queue):
            raise ValueError("请先取入待办，或选择已有订单")
        return self.queue[row]

    def cancel_row(self) -> None:
        row = self.selected_order()
        if row["state"] != "draft":
            raise ValueError("已提交订单不能直接取消；待确认订单同键重试，已出票客票通过查票退票")
        self.outbox.delete_draft(row["id"], self.scope, row["version"])
        self.flow.reset()
        self.update_mode()
        self.refresh_queue()

    async def edit_row(self) -> None:
        row = self.selected_order()
        if row["state"] != "draft":
            raise ValueError("仅未提交待办可以修改旅客；已提交订单的参数保持不变")
        result = await self.modal(
            FormScreen(
                "修改待办旅客",
                [
                    Field("name", "姓名", row["passenger"]),
                    Field("document", "证件库 ID（可空）", str(row["payload"].get("document_id", ""))),
                ],
                "证件库 ID 不为空时，出票姓名由服务端证件记录决定。",
            )
        )
        if result is None:
            return
        payload = sale_payload(row["journey"], result["name"], result["document"])
        passenger = (
            result["name"].strip() if "document_id" not in payload else f"证件 #{payload['document_id']}"
        )
        self.outbox.edit_draft(row["id"], self.scope, row["version"], payload, passenger)
        self.refresh_queue(row["id"])

    async def issue(self) -> None:
        row = self.selected_order()
        if row["state"] == "issued":
            await self.show_ticket(row["ticket"])
            return
        price = (
            money(row["journey"]["amount_minor"], row["journey"].get("currency", "CNY"))
            if (row["state"] == "draft")
            else "按原订单确认，不创建新订单"
        )
        if not await self.modal(
            MessageScreen(
                "确认出票" if row["state"] == "draft" else "确认原出票结果",
                f"{row['label']}\n旅客：{row.get('passenger') or row['payload'].get('passenger') or '证件库旅客'}\n"
                f"报价：{price}\n最近错误：{row.get('last_error') or '无'}\n\n金额和库存以后端为准。没有付款接口，不发生资金扣款。",
                True,
            )
        ):
            return
        if row["state"] == "draft":
            key = self.outbox.promote_draft(row["id"], self.scope, row["version"])
        else:
            key = row["id"]
        self.outbox.started(key)
        self.refresh_queue(key)
        original = self.outbox.get(key)
        try:
            ticket = (
                await self.client.request(
                    "POST", "/api/v1/tickets", payload=original["payload"], idempotency_key=key
                )
            )["data"]
        except APIError as exc:
            self.outbox.failed(key, str(exc), refused=400 <= exc.status < 500)
            raise
        except (SignatureError, httpx.HTTPError, ValueError, KeyError) as exc:
            self.outbox.failed(key, str(exc))
            raise
        self.outbox.complete(key, ticket)
        self.refresh_queue(key)
        self.notify("出票结果已保存：" + ticket["ticket_number"])
        await self.show_ticket(ticket)

    async def details(self) -> None:
        journey = self.selected_journey()
        detail = (await self.client.request("GET", f"/api/v1/trips/{int(journey['id'])}"))["data"]
        names = {s["id"]: s["name"] for s in self.stations}
        lines = [f"班次 #{journey['id']} · UTC"]
        for stop in detail.get("stops", []):
            lines.append(
                f"{stop['seq']:>3}  {names.get(stop['station_id'], stop['station_id'])}\n"
                f"     到 {stop.get('arrival_at', '—')}  开 {stop.get('departure_at', '—')}"
            )
        await self.modal(MessageScreen("逐站时刻", "\n".join(lines)))

    async def ticket(self, number: str = "") -> None:
        if not number:
            result = await self.modal(
                FormScreen(
                    "查询本出票方客票",
                    [
                        Field("number", "13 位票号（保留前导零）"),
                    ],
                )
            )
            if result is None:
                return
            number = result["number"].strip()
        if not re.fullmatch(r"[0-9]{13}", number):
            raise ValueError("票号应为 13 位数字")
        ticket = (await self.client.request("GET", f"/api/v1/tickets/{number}"))["data"]
        self.update_saved_ticket(ticket)
        choice = await self.modal(
            ChoiceScreen(
                "客票 " + number,
                [
                    ("view", f"查看详情 · {ticket['status']} · {ticket.get('passenger', '')}"),
                    ("refund", "整票退票（服务端校验是否已发车及客票状态）"),
                ],
            )
        )
        if choice == "view":
            await self.show_ticket(ticket)
        elif choice == "refund" and await self.modal(
            MessageScreen(
                "确认整票退票",
                f"票号：{number}\n旅客：{ticket.get('passenger', '')}\n"
                f"票价：{money(ticket.get('amount_minor'), ticket.get('currency', 'CNY'))}\n"
                "退还区间库存；本系统没有资金退款接口。",
                True,
            )
        ):
            ticket = (await self.client.request("POST", f"/api/v1/tickets/{number}/refund"))["data"]
            self.update_saved_ticket(ticket)
            await self.show_ticket(ticket)

    def update_saved_ticket(self, ticket: dict) -> None:
        for order in self.outbox.list(self.scope):
            if (order.get("ticket") or {}).get("ticket_number") == ticket["ticket_number"]:
                self.outbox.complete(order["id"], ticket)
        self.refresh_queue()

    async def show_ticket(self, ticket: dict) -> None:
        previous = self.visible_ticket_number
        self.visible_ticket_number = self.last_ticket_number = str(ticket["ticket_number"])
        self.refresh_runtime()
        try:
            await self.show_ticket_contents(ticket)
        finally:
            self.visible_ticket_number = previous
            self.refresh_runtime()

    async def show_ticket_contents(self, ticket: dict) -> None:
        stations = {str(station["id"]): str(station["name"]) for station in self.stations}
        while True:
            screen = ReceiptScreen(ticket, stations, ascii_mode=self.config.ascii)
            await self.modal(screen)
            if screen.choice == "raw":
                await self.modal(
                    MessageScreen("原始客票数据", json.dumps(ticket, ensure_ascii=False, indent=2))
                )
            elif screen.choice == "export":
                default = state_path(False).parent / "receipts" / export_name(ticket)
                form = await self.modal(
                    FormScreen(
                        "导出电子客票",
                        [
                            Field("path", "完整保存路径（.txt 或 .json）", str(default)),
                        ],
                        "TXT 默认隐藏证件号码；JSON 含完整后台数据。已有文件不会被覆盖。",
                    )
                )
                if form is not None:
                    saved = export_ticket(Path(form["path"]), ticket, stations, ascii_mode=self.config.ascii)
                    await self.modal(MessageScreen("已导出", str(saved)))
            else:
                return
