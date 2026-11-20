"""Collect qualitative market claims from a short list of explicit public sources."""
from collections import defaultdict
import re
from urllib.parse import urlsplit

from pydantic import HttpUrl

from context.engine import labelled
from context.web import original_page
from research_models import Claim, Evidence, MarketIntelligence, ReadinessLevel

MARKET_LABELS = {
    "market_definition": r"Marktdefinition|Market definition",
    "target_segment": r"Zielsegment|Target segment",
    "target_geography": r"Zielgeografie|Target geography",
    "growth_drivers": r"Wachstumstreiber|Growth driver",
    "market_risks": r"Marktrisiko|Market risk",
}
MAX_MARKET_SOURCES = 6
READINESS_LABELS = {
    "technology_readiness": (r"TRL|Technology Readiness Level", 9),
    "market_certainty": (r"MCL|Market Certainty Level", 6),
}
EXTRACTABLE_LABELS = MARKET_LABELS | {key: value[0] for key, value in READINESS_LABELS.items()}


def gather_market_sources(research: MarketIntelligence, urls: list[str], *, load_page=original_page):
    """Fill qualitative gaps and preserve the curated research inputs."""
    urls = list(dict.fromkeys(urls))
    if len(urls) > MAX_MARKET_SOURCES:
        raise ValueError(f"Pro Lead sind bis zu {MAX_MARKET_SOURCES} zusätzliche Marktquellen zulässig.")
    result = research.model_copy(deep=True)
    sources = {item.evidence_id: item for item in result.sources}
    found = defaultdict(dict)
    for url in urls:
        signal = load_page(str(HttpUrl(url)))
        if signal is None:
            result.research_gaps.append(f"Marktquelle nicht verfügbar: {url}")
            continue
        matched = False
        for raw_line in signal.evidence.splitlines():
            line = " ".join(raw_line.split())
            if not line or len(line) > 1000:
                continue
            for field, label in EXTRACTABLE_LABELS.items():
                if value := labelled(line, label):
                    item = Evidence(source=urlsplit(str(signal.url)).hostname or signal.source,
                                    url=signal.url, finding=line, field=field, source_date=signal.date,
                                    verification_status="source_matched")
                    if item.evidence_id not in sources and len(sources) >= 50:
                        continue
                    sources.setdefault(item.evidence_id, item)
                    claim = found[field].setdefault(value.casefold(), Claim(
                        value=value, evidence_ids=[item.evidence_id],
                    ))
                    if item.evidence_id not in claim.evidence_ids:
                        claim.evidence_ids.append(item.evidence_id)
                    matched = True
        if not matched:
            result.research_gaps.append(f"Keine strukturiert erkennbare Marktangabe: {signal.url}")
    for field in ("market_definition", "target_segment", "target_geography"):
        claims = found[field]
        if getattr(result, field) is None and len(claims) == 1:
            setattr(result, field, next(iter(claims.values())))
        elif len(claims) > 1:
            result.research_gaps.append(f"Mehrere abweichende Angaben für {field}")
    for field in ("growth_drivers", "market_risks"):
        existing = getattr(result, field)
        known = {claim.value.casefold() for claim in existing}
        existing.extend(claim for key, claim in found[field].items() if key not in known)
    for field, (_, maximum) in READINESS_LABELS.items():
        if getattr(result.sector_metrics, field) is None and len(found[field]) == 1:
            claim = next(iter(found[field].values()))
            match = re.fullmatch(r"([1-9])\s*[–—-]\s*(.+)", claim.value)
            if match and int(match[1]) <= maximum:
                setattr(result.sector_metrics, field, ReadinessLevel(
                    level=int(match[1]), rationale=match[2], evidence_ids=claim.evidence_ids,
                    origin="reported",
                ))
    result.sources = list(sources.values())
    return result
