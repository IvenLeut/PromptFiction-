"""HTTP helper for the fixed external services (OpenAlex, Förderkatalog, Wayback, idw).

Company websites are fetched by `context.web` with its same-site guard; this module is for APIs
whose hosts we choose ourselves. Every request carries a generic User-Agent, a timeout and a size
limit, and goes through the cache so a second run is identical to the first.
"""
from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import logging
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from context.cache import Cache

logger = logging.getLogger(__name__)
USER_AGENT = "FounderRadar/1.0 (research prototype)"
MAX_BYTES = 2_000_000
_last_call: dict[str, float] = {}


class FetchError(Exception):
    """Raised for every transport or decoding failure; callers record it in enrichment_errors."""


def _throttle(host: str, min_interval: float) -> None:
    wait = _last_call.get(host, 0) + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def request(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict | None = None,
            timeout: float = 15, encoding: str | None = None, min_interval: float = 0.5,
            cache: Cache | None = None, retries: int = 2) -> str:
    """Return the response body as text. POST bodies are part of the cache key."""
    host = urllib.parse.urlsplit(url).hostname or ""
    key = "http:" + hashlib.sha1((method + " " + url + " " + (data or b"").decode("latin-1")).encode("utf-8")).hexdigest()
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip", **(headers or {})})
    last = None
    for attempt in range(retries + 1):
        _throttle(host, min_interval)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise FetchError("%s: Antwort größer als %d Bytes" % (host, MAX_BYTES))
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                charset = encoding or resp.headers.get_content_charset() or "utf-8"
                text = body.decode(charset, errors="replace")
                if cache is not None:
                    cache.set(key, text)
                return text
        except HTTPError as e:
            last = FetchError("%s: HTTP %d" % (host, e.code))
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise last
        except (URLError, TimeoutError, http.client.HTTPException, OSError, UnicodeError) as e:
            last = FetchError("%s: %s" % (host, type(e).__name__))
            if attempt < retries:
                time.sleep(1 + attempt)
                continue
    raise last or FetchError(host)


def get_json(url: str, **kw):
    text = request(url, **kw)
    try:
        return json.loads(text)
    except ValueError:
        raise FetchError("%s: keine JSON-Antwort" % (urllib.parse.urlsplit(url).hostname or ""))
