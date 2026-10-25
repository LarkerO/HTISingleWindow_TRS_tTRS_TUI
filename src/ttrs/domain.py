"""Display and input rules independent of terminal widgets."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pypinyin import Style, lazy_pinyin


def parse_date(value: str) -> str:
    value = value.strip()
    pattern = "%Y%m%d" if re.fullmatch(r"[0-9]{8}", value) else "%Y-%m-%d"
    return datetime.strptime(value, pattern).date().isoformat()


def parse_travel_date(value: str, reference=None) -> str:
    """Short dates choose the next matching UTC day, never a silent past date."""
    value = value.strip()
    reference = reference or datetime.now(UTC).date()
    if re.fullmatch(r"\+[0-9]{1,3}", value):
        offset = int(value[1:])
        if offset > 365:
            raise ValueError("相对日期最大支持 +365 天")
        return (reference + timedelta(days=offset)).isoformat()
    if re.fullmatch(r"[0-9]{1,2}", value):
        day = int(value)
        if not 1 <= day <= 31:
            raise ValueError("日期简码须为 1–31")
        for offset in range(12):
            month_index = reference.year * 12 + reference.month - 1 + offset
            year, month = divmod(month_index, 12)
            try:
                candidate = reference.replace(year=year, month=month + 1, day=day)
            except ValueError:
                continue
            if candidate >= reference:
                return candidate.isoformat()
    return parse_date(value)


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def money(amount: object, currency: str = "CNY") -> str:
    if amount is None:
        return "未报价"
    return f"{Decimal(str(amount)) / 100:.2f} {currency}"


def station_matches(station: dict, query: str) -> bool:
    query = query.strip().casefold()
    name = str(station["name"])
    candidates = [
        name,
        station["id"],
        "".join(lazy_pinyin(name)),
        "".join(lazy_pinyin(name, style=Style.FIRST_LETTER)),
    ]
    return any(query in str(value).casefold() for value in candidates)


def sale_payload(journey: dict, passenger: str, document_id: str = "") -> dict:
    if journey.get("fare_available") is False or journey.get("amount_minor") is None:
        raise ValueError("该区间尚无可用报价")
    if int(journey.get("available", 0)) <= 0:
        raise ValueError("该区间无余票，请重新查询")
    payload = {
        "trip_id": int(journey["id"]),
        "origin_seq": int(journey["origin_seq"]),
        "destination_seq": int(journey["destination_seq"]),
    }
    if payload["destination_seq"] <= payload["origin_seq"]:
        raise ValueError("停站序号无效")
    if document_id.strip():
        if not re.fullmatch(r"[0-9]+", document_id.strip()) or int(document_id) <= 0:
            raise ValueError("证件库 ID 必须是正整数")
        payload["document_id"] = int(document_id)
    elif passenger.strip() and len(passenger.strip()) <= 160:
        payload["passenger"] = passenger.strip()
    else:
        raise ValueError("请输入旅客姓名或选择证件库记录")
    if journey.get("fare_version") is not None:
        payload["fare_version"] = int(journey["fare_version"])
    return payload
