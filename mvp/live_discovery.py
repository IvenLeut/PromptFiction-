"""Live legal-entity discovery and cautiously matched company pages."""
from datetime import timedelta
import json
import re
from urllib.parse import urlencode

from free_discovery.core import domain_guesses, gleif_row, industries, registration_conflict
from mvp.scoring import months_before
from mvp.web import canonical_host

ENDPOINT = "https://api.gleif.org/api/v1/lei-records"
PAGE_SIZE = 100
WEBSITE_CHECKS = 8
PAGES_PER_RUN = 4
TECH_HINT = re.compile(
    r"technolog|software|digital|innovati|systems|robot|photon|semicon|biotech|medtech|fintech|data|"
    r"\blabs?\b|\bAI\b|\bKI\b|quantum|automation|health|engineering|energy|materials|sensor", re.I
)
ADMIN_NAME = re.compile(
    r"(?:\b|\.)(?:invest|assetco|beteiligung\w*|immobilien\w*|verwaltung\w*|wirtschaftspr.fung\w*)"
    r"\b|\bcapital\b", re.I
)
COMPANY = re.compile(r"\b(?:GmbH|UG|AG)\b", re.I)
GERMAN_REGISTER = re.compile(r"\bHR[AB]\s*[0-9]", re.I)


def find_candidates(web, options, seen, page=1, *, pages=PAGES_PER_RUN):
    """Page through the LEI subset of German entities, newest first.

    The name only schedules website research. All selected records still reach
    the review list if their product or sector cannot be verified.
    """
    start = months_before(options.as_of, options.max_age_months).isoformat()
    end = options.as_of.isoformat()
    candidates = {}
    entries_read = 0
    for _ in range(pages):
        query = urlencode({
            "filter[entity.legalAddress.country]": "DE",
            "filter[entity.creationDate]": f"{start}..{options.as_of + timedelta(days=1)}",
            "sort": "-entity.creationDate",
            "page[size]": PAGE_SIZE,
            "page[number]": page,
        })
        observation = web.record(f"{ENDPOINT}?{query}", api=True)
        payload = json.loads(observation["text"])
        entries = payload["data"]
        entries_read += len(entries)
        last_page = min(100, payload["meta"]["pagination"]["lastPage"])
        for entry in entries:
            record = gleif_row(entry, start, end)
            if not record or record["id"] in seen or record["administrative_name_flag"]:
                continue
            name = record["name"]
            if ADMIN_NAME.search(name) or not COMPANY.search(name) or not GERMAN_REGISTER.search(record["registration"] or ""):
                continue
            record.update(retrieved_at=observation["retrieved_at"], website=None, industries=[], page_evidence=[])
            candidates[record["id"]] = record
        page = page + 1 if page < last_page else 1
        if page == 1:
            break
    candidates = list(candidates.values())
    candidates.sort(key=lambda record: (
        not bool(industries(record["name"]) or TECH_HINT.search(record["name"])),
        -int(record["founded_on"].replace("-", "")),
        record["id"],
    ))
    return candidates[:WEBSITE_CHECKS], entries_read, page


def find_company_pages(record, web):
    from mvp.context import verify_known_identity
    for url in domain_guesses(record["name"])[:2]:
        pages = web.company_pages(url, limit=3)
        texts = [page["text"] for page in pages]
        if verify_known_identity(record, pages) and not any(registration_conflict(record, text) for text in texts):
            website = pages[0]["url"]
            return website, [page for page in pages if canonical_host(page["url"]) == canonical_host(website)]
    return None, []
