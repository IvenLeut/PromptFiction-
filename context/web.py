"""Read a small selection of public company pages.

`fetch(url, site, cache=None)` keeps the same-site guard (scheme, host, standard port, public IP) and
returns `(final_url, CompanyPage)`. With a `context.cache.Cache` the parsed lines and links are memoised
per URL (requested and final) under `"web:" + sha1(url)`; failures are memoised too (`{"error": ...}`),
so a dead or parked site is not fetched again for the cache's lifetime. Parked / for-sale pages
("Domain for sale", "Buy now $1,470", "Make offer", Sedo, Dan.com) raise `ValueError("Geparkte Domain")`
and never yield text.
"""
import hashlib
import http.client
import ipaddress
import logging
import re
import socket
from functools import lru_cache
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import unquote, urljoin, urlsplit

from models import SourceSignal

logger = logging.getLogger(__name__)
MAX_BYTES = 512_000
PAGE_NAMES = {
    "about", "about-us", "company", "ueber-uns", "über-uns", "team", "founders",
    "product", "products", "produkt", "produkte", "solutions", "loesungen",
    "news", "press", "presse",
}
PRIORITY_PAGES = {"team", "founders", "product", "products", "produkt", "produkte"}
PARKED = re.compile(r"domain (?:is )?for sale|buy this domain|this domain is parked|Make (?:an )?offer|\bSedo\b|"
                    r"Dan\.com|Buy now \$", re.IGNORECASE)
PARKED_ERROR = "Geparkte Domain"
FETCH_ERRORS = (OSError, UnicodeError, ValueError, LookupError, http.client.HTTPException)


class CompanyPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
        self.parts = []
        self.links = []
        self.skipped = None

    def flush(self):
        line = " ".join("".join(self.parts).split())
        if line:
            self.lines.append(line)
        self.parts.clear()

    def handle_starttag(self, tag, attrs):
        if self.skipped:
            return
        if tag in {"script", "style", "template", "noscript"}:
            self.skipped = tag
        if tag in {"p", "br", "li", "div", "h1", "h2", "h3", "h4", "section"}:
            self.flush()
        if tag == "a" and (href := dict(attrs).get("href")):
            self.links.append(href)

    def handle_endtag(self, tag):
        if tag == self.skipped:
            self.skipped = None
        if tag in {"p", "li", "div", "h1", "h2", "h3", "h4", "section"}:
            self.flush()

    def handle_data(self, data):
        if self.skipped is None:
            self.parts.append(data)


def site_key(url):
    return (urlsplit(url).hostname or "").removeprefix("www.").lower()


def is_parked(lines) -> bool:
    """True for domain-parking / for-sale placeholder pages."""
    return bool(PARKED.search(" ".join(lines)))


def parse_page(html: str) -> CompanyPage:
    """Parse HTML into a CompanyPage; a parked / for-sale placeholder raises ValueError("Geparkte Domain")."""
    page = CompanyPage()
    page.feed(html)
    page.close()
    page.flush()
    if is_parked(page.lines):
        raise ValueError(PARKED_ERROR)
    return page


def cache_key(url: str) -> str:
    return "web:" + hashlib.sha1(url.encode("utf-8")).hexdigest()


def _page_from_entry(entry) -> CompanyPage:
    page = CompanyPage()
    page.lines = list(entry.get("lines") or [])
    page.links = list(entry.get("links") or [])
    return page


def fetch(url, site, cache=None):
    """Fetch one page of the company website; see module docstring for the cache behaviour."""
    if cache is not None:
        hit = cache.get(cache_key(url))
        if isinstance(hit, dict) and hit:
            if hit.get("error"):
                raise ValueError(hit["error"])
            return hit.get("url") or url, _page_from_entry(hit)
    try:
        final_url, page = _fetch(url, site)
    except FETCH_ERRORS as exc:
        if cache is not None:
            cache.set(cache_key(url), {"error": str(exc) or type(exc).__name__})
        raise
    if cache is not None:
        entry = {"url": final_url, "lines": page.lines, "links": page.links}
        cache.set(cache_key(url), entry)
        if final_url != url:
            cache.set(cache_key(final_url), entry)
    return final_url, page


def _fetch(url, site):
    return _fetch_window(url, site, int(monotonic() // 900))


@lru_cache(maxsize=64)
def _fetch_window(url, site, _cache_window):
    for _ in range(4):
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not site or site_key(url) != site
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("URL außerhalb der Unternehmenswebsite")
        port = 443 if parsed.scheme == "https" else 80
        if parsed.port not in {None, port}:
            raise ValueError("Nur HTTP-Standardports sind zulässig")
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        ip = ipaddress.ip_address(addresses[0][4][0])
        if not ip.is_global or ip.is_multicast:
            raise ValueError("Zieladresse ist nicht öffentlich")
        cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = cls(parsed.hostname, port, timeout=4)
        # Pin the validated address while keeping the original hostname for TLS.
        connection._create_connection = lambda _address, *args: socket.create_connection(
            (str(ip), port), *args
        )
        try:
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request("GET", path, headers={"User-Agent": "FounderRadar/1.0"})
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308} and response.getheader("Location"):
                url = urljoin(url, response.getheader("Location"))
                continue
            content_type = response.headers.get_content_type()
            if response.status != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"Keine HTML-Seite (HTTP {response.status})")
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("HTML-Seite zu groß")
            return url, parse_page(body.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
        finally:
            connection.close()
    raise ValueError("Zu viele Weiterleitungen")


def company_pages(url, cache=None):
    site = site_key(url)
    pending = [url]
    for index in range(5):
        if index >= len(pending):
            break
        try:
            final_url, page = fetch(pending[index], site, cache=cache)
        except FETCH_ERRORS as exc:
            logger.info("Company page unavailable for %s (%s)", site, type(exc).__name__)
            if index == 0 and str(exc) == PARKED_ERROR:
                break
            continue
        if page.lines:
            yield SourceSignal(source="Unternehmenswebsite", type="website", url=final_url,
                               evidence="\n".join(page.lines))
        if index == 0:
            candidates = {}
            for href in page.links:
                try:
                    link = urljoin(final_url, href)
                    parsed = urlsplit(link)
                    section = unquote(parsed.path.rstrip("/").rsplit("/", 1)[-1]).lower()
                    if site_key(link) == site and section in PAGE_NAMES:
                        clean_link = parsed._replace(fragment="", query="").geturl()
                        if clean_link not in {url, final_url}:
                            candidates[clean_link] = section
                except ValueError:
                    continue
            pending.extend(sorted(candidates, key=lambda link: candidates[link] not in PRIORITY_PAGES))


def original_page(url, cache=None):
    try:
        final_url, page = fetch(url, site_key(url), cache=cache)
    except FETCH_ERRORS:
        logger.info("Original source unavailable for %s", site_key(url))
        return None
    if page.lines:
        return SourceSignal(source="Fundquelle", type="original", url=final_url,
                            evidence="\n".join(page.lines))
    return None
