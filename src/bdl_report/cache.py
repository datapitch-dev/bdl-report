"""SQLite cache of API responses.

BDL data changes at most a few times a year, while the anonymous limit is 100 requests per
15 minutes, so every response is kept for a week by default.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class ResponseCache:
    def __init__(self, path: str | Path = ":memory:", ttl_seconds: float = 7 * 24 * 3600):
        self.ttl = ttl_seconds
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS responses "
            "(key TEXT PRIMARY KEY, body TEXT NOT NULL, stored_at REAL NOT NULL)"
        )

    def get(self, key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT body, stored_at FROM responses WHERE key = ?", (key,)
        ).fetchone()
        if row is None or time.time() - row[1] > self.ttl:
            return None
        return json.loads(row[0])

    def put(self, key: str, body: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO responses VALUES (?, ?, ?)",
            (key, json.dumps(body, ensure_ascii=False), time.time()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
