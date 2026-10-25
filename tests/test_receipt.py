import json
import os
import stat

import pytest
from rich.cells import cell_len

from ttrs.receipt import export_name, export_ticket, format_receipt

TICKET = {
    "ticket_number": "0010000000001",
    "pnr": "ABC123",
    "status": "OPEN",
    "agency_code": "LOCAL",
    "passenger": "旅客[姓名]",
    "amount_minor": 12005,
    "currency": "CNY",
    "passenger_document_snapshot": {"document_type": "ID_CARD", "document_number": "123456789012345678"},
    "coupons": [
        {
            "trip_id": 1,
            "origin_seq": 0,
            "destination_seq": 2,
            "trip": {"train_number": "G101", "operator_code": "LOCAL"},
            "origin": {"station_id": "a", "departure_at": "2026-10-27 23:30:00"},
            "destination": {"station_id": "b", "arrival_at": "2026-10-28 01:20:00"},
        }
    ],
}


@pytest.mark.parametrize("ascii_mode", [False, True])
def test_chinese_frame_alignment_and_masked_document(ascii_mode):
    text = format_receipt(TICKET, {"a": "西安", "b": "南京"}, width=40, ascii_mode=ascii_mode)
    assert "西安 → 南京" in text
    assert "120.05 CNY" in text
    assert "2026-10-28 01:20:00" in text
    assert "123456789012345678" not in text
    assert "5678" in text
    assert {cell_len(line) for line in text.splitlines()} == {44}
    assert "旅客[姓名]" in text
    assert ("+" if ascii_mode else "┌") == text[0]


def test_export_never_overwrites_and_json_is_explicit(tmp_path):
    path = tmp_path / "receipt.txt"
    export_ticket(path, TICKET, {})
    original = path.read_bytes()
    assert "123456789012345678" not in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_ticket(path, {**TICKET, "status": "RFND"}, {})
    assert path.read_bytes() == original
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    target = tmp_path / "raw.json"
    export_ticket(target, TICKET, {})
    assert json.loads(target.read_text(encoding="utf-8")) == TICKET
    with pytest.raises(ValueError):
        export_ticket(tmp_path / "bad.exe", TICKET, {})
    assert export_name(TICKET).startswith("0010000000001-")
