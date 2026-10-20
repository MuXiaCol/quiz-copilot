"""sqlite 答案缓存。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

from .config import DB_PATH


class AnswerCache:
    def __init__(self, path: Path | None = None):
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS answers(
                   key TEXT PRIMARY KEY,
                   payload TEXT NOT NULL,
                   created_at REAL NOT NULL,
                   hits INTEGER NOT NULL DEFAULT 0
               )"""
        )
        self._conn.commit()

    def get(self, key: str) -> dict | None:
        cur = self._conn.execute("SELECT payload FROM answers WHERE key=?", (key,))
        row = cur.fetchone()
        if not row:
            return None
        self._conn.execute("UPDATE answers SET hits=hits+1 WHERE key=?", (key,))
        self._conn.commit()
        try:
            return json.loads(row[0])
        except Exception:
            return None

    def put(self, key: str, payload: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO answers(key, payload, created_at, hits) VALUES(?,?,?,COALESCE((SELECT hits FROM answers WHERE key=?),0))",
            (key, json.dumps(payload, ensure_ascii=False), time.time(), key),
        )
        self._conn.commit()

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0])

    def clear(self) -> None:
        self._conn.execute("DELETE FROM answers")
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


def text_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8", "ignore"))
        h.update(b"\x1f")
    return h.hexdigest()
