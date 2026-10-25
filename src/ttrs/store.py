"""Durable outbox. Commit immutable orders BEFORE sending a POST."""

import json
import os
import sqlite3
import uuid
from pathlib import Path


class Outbox:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        if os.name != "nt" and str(path) != ":memory:":
            path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL,
            label TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
            ticket TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS drafts (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, payload TEXT NOT NULL, label TEXT NOT NULL,
            passenger TEXT NOT NULL, journey TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(orders)")}
        if "last_error" not in columns:
            self.db.execute("ALTER TABLE orders ADD COLUMN last_error TEXT")
        self.db.commit()

    def prepare(self, scope: str, payload: dict, label: str) -> str:
        key = "ttrs-" + uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO orders(id,scope,payload,label) VALUES(?,?,?,?)",
                (key, scope, json.dumps(payload, ensure_ascii=False), label),
            )
        return key

    def save_draft(self, scope: str, payload: dict, label: str, passenger: str, journey: dict) -> str:
        key = "draft-" + uuid.uuid4().hex
        with self.db:
            self.db.execute(
                "INSERT INTO drafts(id,scope,payload,label,passenger,journey) VALUES(?,?,?,?,?,?)",
                (
                    key,
                    scope,
                    json.dumps(payload, ensure_ascii=False),
                    label,
                    passenger,
                    json.dumps(journey, ensure_ascii=False),
                ),
            )
        return key

    def drafts(self, scope: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM drafts WHERE scope=? ORDER BY created_at,rowid", (scope,))
        result = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value["payload"])
            value["journey"] = json.loads(value["journey"])
            value["state"] = "draft"
            result.append(value)
        return result

    def edit_draft(self, key: str, scope: str, version: int, payload: dict, passenger: str) -> None:
        with self.db:
            changed = self.db.execute(
                "UPDATE drafts SET payload=?,passenger=?,version=version+1 WHERE id=? AND scope=? AND version=?",
                (json.dumps(payload, ensure_ascii=False), passenger, key, scope, version),
            ).rowcount
            if not changed:
                raise ValueError("待办已被其他窗口修改或提交，请重新选择")

    def delete_draft(self, key: str, scope: str, version: int) -> None:
        with self.db:
            changed = self.db.execute(
                "DELETE FROM drafts WHERE id=? AND scope=? AND version=?", (key, scope, version)
            ).rowcount
            if not changed:
                raise ValueError("待办已被其他窗口修改或提交，请重新选择")

    def promote_draft(self, key: str, scope: str, version: int) -> str:
        # Acquire the write lock BEFORE reading: two windows cannot promote the same draft twice.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM drafts WHERE id=? AND scope=?", (key, scope)).fetchone()
            if row is None or row["version"] != version:
                raise ValueError("待办已被其他窗口修改或提交，请重新选择")
            order_key = "ttrs-" + uuid.uuid4().hex
            self.db.execute(
                "INSERT INTO orders(id,scope,payload,label) VALUES(?,?,?,?)",
                (order_key, scope, row["payload"], row["label"]),
            )
            self.db.execute("DELETE FROM drafts WHERE id=? AND scope=?", (key, scope))
        return order_key

    def complete(self, key: str, ticket: dict) -> None:
        with self.db:
            self.db.execute(
                "UPDATE orders SET state='issued',ticket=?,last_error=NULL WHERE id=?",
                (json.dumps(ticket, ensure_ascii=False), key),
            )

    def started(self, key: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE orders SET state='pending',last_error=NULL WHERE id=? AND state!='issued'", (key,)
            )

    def failed(self, key: str, message: str, *, refused: bool = False) -> None:
        with self.db:
            self.db.execute(
                "UPDATE orders SET state=?,last_error=? WHERE id=? AND state!='issued'",
                ("blocked" if refused else "pending", message, key),
            )

    def get(self, key: str) -> dict:
        row = self.db.execute("SELECT * FROM orders WHERE id=?", (key,)).fetchone()
        if row is None:
            raise ValueError("本地订单不存在")
        return self.decode(row)

    def list(self, scope: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM orders WHERE scope=? ORDER BY created_at,rowid", (scope,))
        return [self.decode(row) for row in rows]

    @staticmethod
    def decode(row: sqlite3.Row) -> dict:
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        value["ticket"] = json.loads(value["ticket"]) if value["ticket"] else None
        return value

    def close(self) -> None:
        self.db.close()
