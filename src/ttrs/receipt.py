"""Readable, cell-aligned electronic ticket summaries and explicit local exports."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from .domain import display_time, money, stop_label


def clean(value: object) -> str:
    return "".join(c if c.isprintable() else " " for c in str(value))


def receipt_lines(ticket: dict, stations: dict[str, str]) -> list[str]:
    status = {"OPEN": "已出票", "RFND": "已退票"}.get(ticket.get("status"), ticket.get("status", "未提供"))
    lines = [
        "tTRS 电子客票核对单",
        f"票号：{ticket.get('ticket_number', '未提供')}",
        f"PNR：{ticket.get('pnr', '未提供')}   状态：{status}",
        f"旅客：{ticket.get('passenger', '未提供')}",
        f"票价：{money(ticket.get('amount_minor'), ticket.get('currency', 'CNY'))}",
        f"出票方：{ticket.get('agency_code', '未提供')}",
        f"出票时间 UTC：{display_time(ticket.get('issued_at', '未提供'))}",
    ]
    document = ticket.get("passenger_document_snapshot") or {}
    number = str(document.get("document_number", ""))
    if number:
        lines.append(
            f"证件：{document.get('document_type', '')} {'*' * max(4, len(number) - 4)}{number[-4:]}"
        )
    for i, coupon in enumerate(ticket.get("coupons", []), 1):
        origin, destination, trip = (
            coupon.get("origin") or {},
            coupon.get("destination") or {},
            coupon.get("trip") or {},
        )
        origin_name = stop_label(origin, stations)
        destination_name = stop_label(destination, stations)
        lines += [
            "",
            f"乘车联 {i}：{trip.get('train_number') or '班次 #' + str(coupon.get('trip_id', '未提供'))}",
            f"{origin_name} → {destination_name}",
            f"出发 UTC：{display_time(origin.get('departure_at', '未提供'))}",
            f"到达 UTC：{display_time(destination.get('arrival_at', '未提供'))}",
            f"站序：{coupon.get('origin_seq', '—')} → {coupon.get('destination_seq', '—')}",
            f"承运方：{trip.get('operator_code', '未提供')}",
        ]
    lines += [
        "",
        "用于核对电子客票，不是实体纸票或付款凭证。",
        "客票状态可能变化，请以服务端最新查询结果为准。",
    ]
    return [clean(line) for line in lines]


def format_receipt(
    ticket: dict, stations: dict[str, str], *, width: int = 64, ascii_mode: bool = False
) -> str:
    width = max(24, width)
    console = Console(width=width, force_terminal=False)
    if ascii_mode:
        tl, tr, bl, br, vertical, horizontal = "+", "+", "+", "+", "|", "-"
    else:
        tl, tr, bl, br, vertical, horizontal = "┌", "┐", "└", "┘", "│", "─"
    result = [tl + horizontal * (width + 2) + tr]
    for line in receipt_lines(ticket, stations):
        for text in Text(line).wrap(console, width, overflow="fold") or [Text("")]:
            value = text.plain
            result.append(vertical + " " + value + " " * (width - cell_len(value)) + " " + vertical)
    result.append(bl + horizontal * (width + 2) + br)
    return "\n".join(result)


def export_ticket(path: Path, ticket: dict, stations: dict[str, str], *, ascii_mode: bool = False) -> Path:
    path = path.expanduser()
    if path.suffix.lower() not in {".txt", ".json"}:
        raise ValueError("导出路径扩展名应为 .txt 或 .json")
    content = (
        json.dumps(ticket, ensure_ascii=False, indent=2)
        if path.suffix.lower() == ".json"
        else format_receipt(ticket, stations, ascii_mode=ascii_mode)
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation prevents silently overwriting an existing export.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    return path.resolve()


def export_name(ticket: dict) -> str:
    number = "".join(c for c in str(ticket.get("ticket_number", "")) if c.isascii() and c.isdigit())
    if len(number) != 13:
        raise ValueError("客票缺少有效的 13 位票号")
    return number + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".txt"
