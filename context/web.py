"""Read a small selection of public company pages."""
import http.client
import ipaddress
import logging
import socket
from html.parser import HTMLParser
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


def fetch(url, site):
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
            page = CompanyPage()
            page.feed(body.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
            page.close()
            page.flush()
            return url, page
        finally:
            connection.close()
    raise ValueError("Zu viele Weiterleitungen")


def company_pages(url):
    site = site_key(url)
    pending = [url]
    for index in range(5):
        if index >= len(pending):
            break
        try:
            final_url, page = fetch(pending[index], site)
        except (OSError, UnicodeError, ValueError, LookupError, http.client.HTTPException) as exc:
            logger.info("Company page unavailable for %s (%s)", site, type(exc).__name__)
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


def original_page(url):
    try:
        final_url, page = fetch(url, site_key(url))
    except (OSError, UnicodeError, ValueError, LookupError, http.client.HTTPException):
        logger.info("Original source unavailable for %s", site_key(url))
        return None
    if page.lines:
        return SourceSignal(source="Fundquelle", type="original", url=final_url,
                            evidence="\n".join(page.lines))
    return None
