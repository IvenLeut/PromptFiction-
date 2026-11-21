"""Small SQLite cache for HTTP and model calls (plan v4: every external call goes through the cache).

Keyed by an arbitrary string, values are JSON. Entries expire after `ttl_hours`. The cache file
lives in `.cache/context.db` (git-ignored) unless CONTEXT_CACHE points elsewhere; set
CONTEXT_CACHE=off to disable. A cache makes a second run identical to the first and keeps us
within the rate limits of OpenAlex, the Förderkatalog and Wayback.

Caching layers of step 2 (all persistent ones share one `Cache`, passed as `lookups["cache"]`):

| layer                                   | key                         | scope                         |
|-----------------------------------------|-----------------------------|-------------------------------|
| `context.http.request` (idw, OpenAlex,  | `http:` + sha1(method, url, | persistent, raw response text |
|  Wayback, Google Patents)               |  body), `http.cache_key`    |                               |
| `context.foekat._cached_fetch`          | `foekat:` + method/url/body | persistent, raw catalogue page|
| `context.web.fetch` (website, Impressum)| `web:` + sha1(url)          | persistent, parsed lines/links and failures |
| `context.imprint.imprint_lookup`        | `imprint:` + sha1(website)  | persistent, found Impressum text or miss |
| `context.website_match.match_lookup`    | `website_match:v9:` + sha1(lead context), `dns:` + host | persistent, verified candidates (only complete runs) / DNS result |
| `context.web._fetch_window`            | `lru_cache(64)` per URL     | in-process, 15-minute window  |
| `context.classify.classify_texts`       | `classify:` + prompt hash   | persistent, model answer      |
| `context.engine.cached_quotes`          | `quotes:` + sha1(texts)     | persistent, Ollama quotes     |
| `context.ollama.request_quotes`         | `lru_cache(128)` per call   | in-process                    |

The two in-process `lru_cache`s are not redundant: they also apply when no `Cache` is passed (CLI `--no-lookups`,
a custom enricher without lookups), where the persistent layers are skipped.
`NoCache()` disables the persistent layers without touching the disk (tests; `default_lookups(cache=None)`).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = Path(".cache") / "context.db"


class Cache:
    """JSON values in one SQLite table; the file is opened on first use."""

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
        """The stored value, or None if missing, expired or the cache is off."""
        if not self.enabled:
            return None
        row = self._db().execute("SELECT value, ts FROM cache WHERE key = ?", (key,)).fetchone()
        if row is None or time.time() - row[1] > self.ttl:
            return None
        return json.loads(row[0])

    def set(self, key: str, value) -> None:
        """Store a JSON-serialisable value (no-op when off)."""
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
    """A disabled cache: never opens a file."""

    def __init__(self):
        super().__init__("off")
