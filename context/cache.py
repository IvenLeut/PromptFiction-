"""Small SQLite cache for HTTP and model calls (plan v4: every external call goes through the cache).

Keyed by an arbitrary string, values are JSON. Entries expire after `ttl_hours`. The cache file
lives in `.cache/context.db` (git-ignored) unless CONTEXT_CACHE points elsewhere; set
CONTEXT_CACHE=off to disable. A cache makes a second run identical to the first and keeps us
within the rate limits of OpenAlex, the Förderkatalog and Wayback.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = Path(".cache") / "context.db"


class Cache:
    def __init__(self, path: str | os.PathLike | None = None, ttl_hours: float = 24 * 14):
        target = os.environ.get("CONTEXT_CACHE") if path is None else str(path)
        self.enabled = target != "off"
        self.ttl = ttl_hours * 3600
        self.path = Path(target) if target and target != "off" else DEFAULT_PATH
        self._con = None

    def _db(self):
        if self._con is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._con = sqlite3.connect(str(self.path))
            self._con.execute("CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, value TEXT NOT NULL, ts REAL NOT NULL)")
        return self._con

    def get(self, key: str):
        if not self.enabled:
            return None
        row = self._db().execute("SELECT value, ts FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or time.time() - row[1] > self.ttl:
            return None
        return json.loads(row[0])

    def set(self, key: str, value) -> None:
        if not self.enabled:
            return
        self._db().execute("INSERT OR REPLACE INTO cache(key, value, ts) VALUES (?, ?, ?)",
                           (key, json.dumps(value, ensure_ascii=False, default=str), time.time()))
        self._db().commit()

    def memo(self, key: str, compute):
        """Return the cached value for `key`, or compute, store and return it. Exceptions are not cached."""
        hit = self.get(key)
        if hit is not None:
            return hit
        value = compute()
        if value is not None:
            self.set(key, value)
        return value


class NoCache(Cache):
    def __init__(self):
        super().__init__("off")
