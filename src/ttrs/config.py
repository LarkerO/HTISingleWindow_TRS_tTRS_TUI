import math
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Invalid user configuration, reported before starting the terminal UI."""


@dataclass
class Config:
    base_url: str = "http://127.0.0.1:8000"
    agency_code: str = ""
    ascii: bool = False
    timeout: float = 20.0
    keys: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.base_url, str) or not isinstance(self.agency_code, str):
            raise ConfigError("base_url 和 agency_code 必须为字符串")
        if not isinstance(self.ascii, bool):
            raise ConfigError("ascii 必须为 true 或 false")
        if (
            isinstance(self.timeout, bool)
            or not isinstance(self.timeout, (int, float))
            or not math.isfinite(self.timeout)
            or not 1 <= self.timeout <= 120
        ):
            raise ConfigError("timeout 必须在 1–120 秒之间")
        actions = {
            "focus_date",
            "focus_train",
            "origin",
            "destination",
            "passenger",
            "select_row",
            "menu",
            "search",
            "take",
            "issue",
            "cancel_row",
            "ticket",
            "connect",
            "details",
            "quit",
            "documents",
            "help",
            "normal_sale",
            "roundtrip",
            "connection",
            "edit_row",
            "mode",
        }
        if not isinstance(self.keys, dict) or any(
            key not in actions or not isinstance(value, str) or not value.strip()
            for key, value in self.keys.items()
        ):
            raise ConfigError("keys 必须为已知动作名到非空键名的映射")

    @classmethod
    def load(cls, path: Path | None):
        data = tomllib.loads(path.read_text(encoding="utf-8-sig")) if path else {}
        allowed = {"base_url", "agency_code", "ascii", "timeout", "keys"}
        if set(data) - allowed:
            raise ConfigError("配置包含未知字段；密钥请使用环境变量或连接窗口")
        return cls(**data)


def state_path(demo: bool) -> Path:
    if demo:
        return Path(":memory:")
    override = os.environ.get("TTRS_STATE_DIR")
    if override:
        return Path(override) / "orders.sqlite3"
    base = Path(
        os.environ.get(
            "LOCALAPPDATA", Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        )
    )
    return base / "tTRS" / "orders.sqlite3"
