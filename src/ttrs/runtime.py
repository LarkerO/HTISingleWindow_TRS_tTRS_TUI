"""Local process samples and truthful runtime status; no synthetic ticket numbers."""

import time
from dataclasses import dataclass
from datetime import datetime

import psutil


@dataclass
class Usage:
    cpu_percent: float | None = None
    memory_rss: int | None = None


class ProcessMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.usage = Usage()
        self.last_sample = time.monotonic()
        try:
            self.process.cpu_percent(interval=None)
            self.usage.memory_rss = self.process.memory_info().rss
        except (psutil.Error, OSError):
            pass

    def sample(self) -> Usage:
        current = time.monotonic()
        if current - self.last_sample < 1:
            return self.usage
        self.last_sample = current
        try:
            self.usage.cpu_percent = self.process.cpu_percent(interval=None)
            self.usage.memory_rss = self.process.memory_info().rss
        except (psutil.Error, OSError):
            self.usage = Usage()
        return self.usage


def milliseconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}ms"


def format_status(
    usage: Usage,
    metrics,
    ticket_number: str,
    operations: int,
    *,
    local: bool = False,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now().astimezone()
    clock = now.strftime("%Y-%m-%d %H:%M:%S %z")
    cpu = "—" if usage.cpu_percent is None else f"{usage.cpu_percent:.1f}%"
    memory = "—" if usage.memory_rss is None else f"{usage.memory_rss / 1024**2:.1f}MiB"
    network = "本地" if local else metrics.label if metrics else "未连接"
    rtt = None if local or metrics is None else metrics.roundtrip_ms
    server = None if local or metrics is None else metrics.server_ms
    return (
        f"本地时间 {clock} | 客户端CPU {cpu} | 内存RSS {memory}\n"
        f"本张票号 {ticket_number} | 下一张票号 出票时生成 | 累计操作 {operations}\n"
        f"网络 {network} | 服务器往返 {milliseconds(rtt)} | 上次服务处理 {milliseconds(server)}"
    )
