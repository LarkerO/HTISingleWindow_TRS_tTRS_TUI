"""Continuous entry helpers. Each leg remains an independent backend ticket."""

from dataclasses import dataclass
from datetime import UTC, datetime


def utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@dataclass
class JourneyFlow:
    mode: str = "normal"
    legs: int = 0
    earliest: datetime | None = None

    def reset(self, mode: str = "normal") -> None:
        if mode not in {"normal", "roundtrip", "connection"}:
            raise ValueError("未知连续录入模式")
        self.mode, self.legs, self.earliest = mode, 0, None

    def advance(self, origin: dict, destination: dict, arrival: str) -> tuple[dict, dict | None] | None:
        if self.mode == "normal":
            return None
        arrived = utc_time(arrival)
        if self.mode == "roundtrip" and self.legs == 1:
            self.reset()
            return None
        self.legs += 1
        self.earliest = arrived
        return dict(destination), dict(origin) if self.mode == "roundtrip" else None

    def window(self, date: str) -> dict[str, str]:
        if self.earliest is None:
            return {}
        if date < self.earliest.date().isoformat():
            raise ValueError("后续行程日期不能早于上一程到达日期（UTC）")
        if date == self.earliest.date().isoformat():
            return {"time_from": self.earliest.strftime("%H:%M:%S")}
        return {}

    def accepts(self, departure: str) -> bool:
        return self.earliest is None or utc_time(departure) >= self.earliest

    @property
    def label(self) -> str:
        title = {"normal": "普通售票", "roundtrip": "往返录入", "connection": "联程录入"}[self.mode]
        if self.earliest:
            title += " · 后续出发不早于 " + self.earliest.strftime("%m-%d %H:%M:%S UTC")
        return title
