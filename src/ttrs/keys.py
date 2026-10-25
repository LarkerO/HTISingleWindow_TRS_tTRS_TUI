from typing import ClassVar

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import RichLog, Static

from .config import Config


class KeyApp(App):
    def __init__(self, *, title: str | None = None):
        super().__init__()
        self.title = title or Config().window_title

    BINDINGS: ClassVar[list[Binding]] = [Binding("ctrl+q", "quit", "退出")]
    CSS = "RichLog { border: solid cyan; height: 1fr; } Static { height: 3; }"

    def compose(self) -> ComposeResult:
        yield Static(
            "按下待测快捷键，下方显示收到的键名。没有记录通常表示被宿主拦截。\nCtrl+Q 退出；此页面不用于输入密钥。",
            markup=False,
        )
        yield RichLog(id="keys", markup=False)

    def on_key(self, event: events.Key) -> None:
        self.query_one(RichLog).write(f"key={event.key!r} character={event.character!r}")
