"""Bounded public-page retrieval using the existing robots/SSRF guarded collector."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import requests
from bs4 import BeautifulSoup
from free_discovery.network import Fetcher, parse_html
from mvp.contracts import Source


def canonical_host(url):
    return (urlsplit(url).hostname or '').lower().removeprefix('www.')


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss'))


class Web:
    def __init__(self, root, *, offline=False, refresh=False):
        self.root = Path(root)
        self.fetcher = Fetcher(self.root, offline=offline)
        self.refresh = refresh
        self.offline = offline
        self.calls = 0
        self.network_calls = 0
        self.cache_hits = 0
        self.errors = []
        self.seen = {}

    def record(self, url, *, api=False):
        url = requests.Request('GET', url).prepare().url
        # A new live run retries transient failures and refreshes yesterday's pages.
        path = self.root / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if self.refresh and path.exists() and not self.offline:
            path.unlink()
        self.calls += 1
        if path.exists():self.cache_hits+=1
        elif not self.offline:self.network_calls+=1
        return self.fetcher.get(url, api=api, timeout=12 if api else 7, max_bytes=3_000_000 if api else 2_000_000)

    def page(self, url, kind='company'):
        if url in self.seen:
            return self.seen[url]
        rec = self.record(url)
        parsed = parse_html(rec['text'], rec['url'])
        soup = BeautifulSoup(rec['text'], 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else canonical_host(url)
        # Keep navigation for link discovery, remove it from semantic extraction.
        body = BeautifulSoup(rec['text'], 'html.parser')
        for el in body(['nav','header','script','style','noscript','svg','template']):el.decompose()
        body_text = parse_html(str(body),rec['url'])['text']
        page = {**parsed, 'text':body_text, 'url': rec['url'], 'html': rec['text'], 'source': Source(
            url=rec['url'], title=title, retrieved_at=rec['retrieved_at'], sha256=rec['sha256'], kind=kind)}
        self.seen[url] = page
        return page

    def try_page(self, url, kind='company'):
        try:
            return self.page(url, kind)
        except Exception as ex:
            self.errors.append({'url': url, 'error': type(ex).__name__ + ': ' + str(ex)[:180]})
            return None

    def company_pages(self, url, limit=5):
        first = self.try_page(url)
        if not first:
            return []
        host = canonical_host(first['url'])
        links = [u for u in first['links'] if canonical_host(u) == host and not urlsplit(u).fragment
                 and re.search(r'impress|imprint|legal|about|ueber|über|unternehmen|produkt|product|technolog|solution|team', u, re.I)
                 and not re.search(r'privacy|datenschutz|\.pdf|\?', u, re.I)]
        def page_priority(url):
            path = urlsplit(url).path
            if re.search(r'impress|imprint|legal', path, re.I):
                return 0
            if re.search(r'team|about|ueber|über|unternehmen', path, re.I):
                return 1
            return 2

        links.sort(key=lambda u: (page_priority(u), len(u), u))
        if not any(re.search(r'impress|imprint|legal', u, re.I) for u in links):
            links.insert(0, urljoin(first['url'], '/impressum'))
        pages = [first]
        for link in dict.fromkeys(links):
            if len(pages) >= limit:
                break
            if link.rstrip('/') == first['url'].rstrip('/'):
                continue
            page = self.try_page(link)
            if page and canonical_host(page['url']) == host and page['url'] not in [p['url'] for p in pages]:
                pages.append(page)
        return pages


def excerpt(text, start, max_words=20):
    # Short verbatim evidence only; never save whole pages into exported dossiers.
    words=list(re.finditer(r'\S+',text))
    position=next((i for i,m in enumerate(words) if m.end()>start),0)
    begin=max(0,position-3)
    return ' '.join(m.group() for m in words[begin:begin+max_words])
