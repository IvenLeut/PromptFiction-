"""Extract bounded excerpts from verified public company pages for team research."""
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from bs4 import BeautifulSoup

from mvp.contracts import TeamEvidence
from mvp.web import canonical_host, normalized

ROLE = re.compile(r"\b(?:co[- ]?founder|founder|gründ(?:er|erin|ungsteam)|geschäftsführ\w*|CEO|CTO|CFO|CIO)\b", re.I)
NAME = re.compile(r"^(?:(?:Dr\.-Ing\.|Dr\.|Prof\.)\s+)*(?:[A-ZÄÖÜ][\wÀ-ž.'’\-]+\s+){1,4}[A-ZÄÖÜ][\wÀ-ž.'’\-]+$")
BIOGRAPHY = re.compile(r"\b(?:studier\w*|studied|university|universität|hochschule|degree|PhD|forschung|research|experience|erfahrung|engineering)\b", re.I)
TEAM_SOURCES = json.loads((Path(__file__).resolve().parents[1] / "config/team_sources.json").read_bytes())


def extract_team(dossier, pages):
    if not dossier.website or dossier.identity_status != "verified":
        return
    host = canonical_host(dossier.website)
    observations = []
    for page in pages:
        if canonical_host(page["url"]) != host:
            continue
        path = urlsplit(page["url"]).path.casefold()
        if re.search(r"privacy|datenschutz|impress|imprint|legal", path):
            continue
        lines = [" ".join(line.split()) for line in page["text"].splitlines() if line.strip()]
        soup = BeautifulSoup(page.get("html", ""), "html.parser")
        profiles = []
        for anchor in soup.select("a[href]"):
            try:
                url = urljoin(page["url"], anchor["href"])
                parsed = urlsplit(url)
            except ValueError:
                continue
            if parsed.scheme == "https" and not parsed.username and canonical_host(url) == "linkedin.com":
                if parsed.path.startswith("/in/"):
                    profiles.append(url)
        for index, line in enumerate(lines):
            if not ROLE.search(line) or len(line) > 210:
                continue
            if index == 0 or not NAME.fullmatch(lines[index-1]):
                continue
            candidate = lines[index-1]
            short_name = re.sub(r"^(?:(?:Dr\.-Ing\.|Dr\.|Prof\.)\s+)+", "", candidate)
            profile_url = next((url for url in profiles if normalized(urlsplit(url).path[4:]).startswith(normalized(short_name))), None)
            after = lines[index+1:index+3]
            bio = next((text for text in after if 40 <= len(text) <= 500 and
                        not NAME.fullmatch(text) and not ROLE.search(text)), "")
            observations.append(TeamEvidence(
                name=candidate, role=line, biography=" ".join(bio.split()[:24]),
                source=page["source"], profile_url=profile_url,
            ))
        if not observations and ("team" in path or "about" in path or "ueber-" in path):
            matched = [line for line in lines if (ROLE.search(line) or BIOGRAPHY.search(line)) and 60 <= len(line) <= 450]
            if matched:
                observations.append(TeamEvidence(
                    name="", role="", biography=" ".join(matched[0].split()[:24]), source=page["source"]
                ))
    unique = {}
    for evidence in observations:
        key = (evidence.name.casefold(), evidence.source.url)
        unique.setdefault(key, evidence)
    dossier.team_evidence = list(unique.values())[:10]


def collect_team_references(dossier, web):
    """Match known team names against verified institutional pages."""
    names = {item.name for item in dossier.team_evidence if item.name}
    if not names or not dossier.website:
        return
    for url in TEAM_SOURCES.get(canonical_host(dossier.website), []):
        page = web.try_page(url, "team_institution")
        if not page or canonical_host(page["url"]) != canonical_host(url):
            continue
        for name in sorted(names):
            short_name = re.sub(r"^(?:(?:Dr\.-Ing\.|Dr\.|Prof\.)\s+)+", "", name)
            match = re.search(r"(?<!\w)" + re.escape(short_name) + r"(?!\w)", page["text"], re.I)
            if match:
                dossier.team_evidence.append(TeamEvidence(
                    name=name, role="", biography=page["source"].title + " · " + match.group(0),
                    source=page["source"],
                ))
