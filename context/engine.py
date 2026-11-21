"""Extract evidenced facts from sourcing signals and public company pages.

Two layers:
1. Rule extraction over all collected texts (this file, label/value patterns, no network).
2. Optional lookups against fixed public sources (Impressum, Förderkatalog, OpenAlex, Wayback, idw,
   Google Patents) and the local Ollama classifier, see context/ENRICHMENT.md. They run only when
   `lookups` is passed (CLI: default on, `--offline` off), so unit tests stay offline.

`enrich` is the only entry point; the private helpers below follow its order: collect texts, run the
lookups, extract rule facts, classify, model quotes, derive statuses and questions, assemble context_v2.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field as dc_field
from datetime import date
from decimal import Decimal
from functools import partial

from context.company import (
    FOUNDER_FIELDS, FUNDING_EVENTS, FUNDING_FIELDS, PRODUCT_FIELDS,
    RESEARCH_LABELS, TRACTION_EVENTS, TRACTION_METRICS,
)
from context.idw import fold as idw_fold, name_pattern
from context.lookup import (
    MODEL_QUOTE_PREFIX, PRESS_NAMESAKE_YEARS, SOURCE_FOEKAT, SOURCE_IDW_MENTION, SOURCE_SOURCING, Lookup,
)
from context.text import GERMAN_DATE, german_date, strip_persons, years_before
from context.web import company_pages
from models import EnrichedLead, Evidence, FounderProfile, Grant, RawLead, SourceSignal
from research_models import (
    Claim, CompanyResearch, ContextV2, FounderResearch, FundingResearch, MarketMeasure, Period,
    ProductResearch, ResearchStatus, TractionResearch,
)
from scoring_input import build_scoring_input, source_binding

logger = logging.getLogger(__name__)
EXIST_CONFIRMED_YEARS = 3   # an EXIST mention on the site explains a Wayback capture at most this long before the project
MAX_TEAM_OPENALEX = 3       # OpenAlex lookups for new persons from the team lookup per lead
OPENALEX_TECH_WORKS = 5     # an OpenAlex profile with this many works counts as tech background (agreed with scorer)
SOURCE_OPENALEX_LABEL = "OpenAlex"
MAX_DIRECTOR_LOOKUPS = 3    # OpenAlex lookups for Impressum managing directors per lead (1 call each, ~100 calls/day without key)
DIRECTOR_ROLE = "Geschäftsführung (Impressum)"
WEBSITE_TEXT_CHARS = 5000   # Evidence field="website_text" for the scorer's noise filter
MAX_FINDING = 1000      # characters of a text kept as Evidence.finding (same cap as Lookup.add)
SUMMARY_CHARS = 200     # sourcing signals shorter than this are one-line summaries, never classified
STOPWORDS = set("""für mit und oder der die das des dem den ein eine einer eines einem einen von zur zum auf aus bei nach über unter durch
ohne gegen sowie auch nicht sind wird werden wurde kann können soll sollen haben hat ist sein ihre ihrer seine seiner unsere unser
entwickelt entwickeln bietet bieten ermöglicht basierend neue neuen neuer innovative innovativ lösung lösungen plattform software system
systeme technologie unternehmen startup start-up produkt produkte kunden projekt the and for with from that this into using based
develops developing provides solution solutions platform company customers product products technology
förderempfänger bundesanteil ausführende stelle förderkennzeichen laufzeit exist-gründungsstipendium-projekt
forschungstransfer gründungsstipendium fkz exist-forschungstransfer exist-gründungsstipendium fördersumme
öffentliche förderung programm thema""".split())
CATALOGUE_TYPES = {"exist_projekt", "foerderprojekt"}
# Catalogue rows, archive stubs and sourcing summaries are not quotable: they would turn a grant sum into "capital need".
UNQUOTABLE_TYPES = CATALOGUE_TYPES | {"wayback", "sourcing", "demo"}
CATALOGUE_LABELS = {
    "fkz": r"Förderkennzeichen|FKZ", "programme": r"Programm", "thema": r"Thema", "recipient": r"Förderempfänger",
    "executing": r"Ausführende Stelle", "period": r"Laufzeit", "amount": r"Fördersumme|Summe",
}


LABELS = {
    "target_customers": r"Zielkund(?:en|schaft)|Zielgruppe|Target customers|Target audience",
    "customer_problem": r"Problem(?:stellung)?|Kundenproblem|Customer problem|Customer need",
    "solution": r"Lösung|Unsere Lösung|Solution|Our solution",
    "market": r"Markt|Zielmarkt|Market|Target market",
    "technology": r"Technologie|Technology",
    "competition": r"Wettbewerb|Wettbewerber|Competition|Competitors",
    "sales": r"Vertrieb|Vertriebskanäle|Sales channels|Go-to-market",
    "capital_need": r"Weiterer Kapitalbedarf|Kapitalbedarf|Additional capital needed",
    "funding_stage": r"Finanzierungsphase|Funding stage",
}
PROSE = {
    "target_customers": r"(?:Unsere (?:Lösung|Plattform|Software) richtet sich an|"
                        r"Our (?:solution|platform|software) is designed for)\s+(.+)",
    "customer_problem": r"(?:Das Problem unserer Kunden ist|The problem our customers face is)\s+(.+)",
    "solution": r"(?:Wir entwickeln|We are developing)\s+(.+)",
}
PRODUCT_STAGES = {
    "idee": r"Idee|Idea|Konzept|Concept",
    "paper": r"Paper|Forschungsarbeit",
    "labor_prototyp": r"Laborprototyp|Labor-Prototyp|Lab prototype",
    "prototyp": r"Prototyp|Prototype",
    "mvp": r"MVP|Minimum viable product",
    "pilot": r"Pilot|Pilotprojekt|Pilot phase|Pilotphase",
    "erste_kunden": r"Erste Kunden|First customers",
    "am_markt": r"Am Markt|Marktreif und verfügbar|Commercial|Commercially available|On the market|Launched",
}
FUNDING = {
    "vc_backed": r"VC[- ]finanziert|VC[- ]backed|Venture[- ]capital[- ]backed",
    "non_vc_funded": r"Bootstrapped|Eigenfinanziert|Fördermittel erhalten|Grant-funded",
    "unfunded": r"Unfinanziert|Unfunded|Keine Finanzierung|No funding",
    "funded": r"Finanziert|Funded",
}
MONEY_LABELS = {
    "round_size_eur": r"Rundengröße|Round size",
    "asking_pre_money_eur": r"Geforderte Pre-Money-Bewertung|Asking pre-money valuation",
}
PERIOD_METRICS = {
    "revenue": (r"Jahresumsatz|Annual revenue", "pro Jahr", "EUR"),
    "revenue_growth": (r"Umsatzwachstum|Revenue growth", "%", None),
    "customer_count": (r"Kundenanzahl|Customer count", "Kunden", None),
}
QUESTIONS = {
    "market": "Welchen Markt adressiert ihr und wie grenzt ihr ihn ab?",
    "technology": "Was ist der technische Ansatz und welche Nachweise gibt es?",
    "competition": "Welche Alternativen nutzen eure Zielkunden heute?",
    "sales": "Über welche Kanäle gewinnt ihr Kunden?",
    "capital_need": "Welchen Kapitalbedarf habt ihr nach dieser Runde?",
    "round_size_eur": "Wie groß ist die geplante Runde in Euro?",
    "asking_pre_money_eur": "Welche Pre-Money-Bewertung fordert ihr in Euro?",
}
PRODUCT_STAGE_LABEL = "Produktreife|Produktstatus|Product stage"
FUNDING_STATUS_LABEL = "Finanzierungsstatus|Funding status"
VC_STATUS_LABEL = "VC-Status|VC status"
ROUND_CLOSED = re.compile(r"Wir haben (?:unsere|eine) (Pre-Seed|Seed|Series [A-Z])[- ]Runde abgeschlossen[.!]?"
                          r"|We (?:have )?closed (?:our|a) (Pre-Seed|Seed|Series [A-Z]) round[.!]?", re.IGNORECASE)
FOUNDER_ROLE = r"(CEO|CTO|COO|CFO|CPO|Co-Founder|Co-Gründer(?:in)?|Geschäftsführer(?:in)?)"
FOUNDING_WORDS = re.compile(r"(?i)\bgegründet\b|\bGründung (von|der) |was founded|founded in|has been founded")
FOUNDING_PLANNED = re.compile(r"(?i)geplant|planen|plant |gegründet werden|soll|wird gegründet|bereitet .* vor|"
                              r"vorbereitet|in Gründung|zu gründen")
# Fields that enrich sets itself; a lookup must not override them through `Lookup.fields`.
OWN_FIELDS = {"evidence", "founder_profiles", "research_questions", "product_stage", "funding_status", "vc_status",
              "first_signal_date", "enrichment_sources", "enrichment_errors", "grants", "patents"}
_DEFAULT_CACHE = object()


def euros(text: str) -> int | None:
    """'€ 1.500.000', '2,5 Mio. EUR', '800 Tsd. €' -> whole euros; None without currency or for other text."""
    match = re.fullmatch(r"(?:€\s*(.+)|(.+?)\s*(?:EUR|€))\.?", text, re.IGNORECASE)
    if match:
        amount = (match[1] or match[2]).strip().rstrip(".")
        if re.fullmatch(r"[1-9]\d{0,2}([., ])\d{3}(?:\1\d{3}){0,3}|[1-9]\d{0,14}|0", amount):
            return int(re.sub(r"[., ]", "", amount))
        scaled = re.fullmatch(r"(\d{1,6}(?:[,.]\d{1,3})?)\s*(Mio\.?|million|Tsd\.?|thousand)",
                              amount, re.IGNORECASE)
        if scaled:
            multiplier = 1000 if scaled[2].lower().startswith(("tsd", "thousand")) else 1_000_000
            return int(Decimal(scaled[1].replace(",", ".")) * multiplier) or None
    return None


def stage_value(text: str, choices: dict[str, str]) -> str | None:
    """The key of the first pattern in `choices` that matches the whole text (trailing ' .' ignored)."""
    for value, pattern in choices.items():
        if re.fullmatch(pattern, text.strip(" ."), re.IGNORECASE):
            return value
    return None


HEADINGS = "|".join(LABELS.values())
STATEMENT_HEADINGS = "|".join([*LABELS.values(), *MONEY_LABELS.values(), *RESEARCH_LABELS.values(),
                               PRODUCT_STAGE_LABEL, FUNDING_STATUS_LABEL + "|" + VC_STATUS_LABEL])


def labelled(line: str, labels: str) -> str | None:
    """The value of a 'Label: value' line for one of `labels` (regex alternatives), else None."""
    match = re.fullmatch(rf"(?:{labels})\s*[:–]\s*(.+)", line, re.IGNORECASE)
    if not match:
        return None
    value = match[1].strip()
    # Reject repeated headings and navigation labels. Capitalisation alone is not
    # evidence of navigation: German nouns such as "Drahtlose Sensorik" are valid facts.
    if re.fullmatch(rf"(?:{HEADINGS})", value, re.IGNORECASE):
        return None
    words = value.split()
    navigation = {"projects", "knowledge", "base", "news", "careers", "home", "about", "contact",
                  "menu", "navigation", "projekte", "kontakt", "karriere", "startseite"}
    if 2 <= len(words) <= 4 and all(w.casefold() in navigation for w in words):
        return None
    return value


def statements(signal: SourceSignal) -> Iterable[str]:
    """Each line of a text block, plus 'Heading: next line' when a line is only a recognised label."""
    lines = [" ".join(line.split()) for line in signal.evidence.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        yield line
        if (i + 1 < len(lines) and re.fullmatch(STATEMENT_HEADINGS, line, re.IGNORECASE)
                and not re.fullmatch(STATEMENT_HEADINGS, lines[i + 1], re.IGNORECASE)):
            yield f"{line}: {lines[i + 1]}"


def field_terms(lead: RawLead, limit: int = 6) -> list[str]:
    """Search terms for 'papers in the product field': the most specific words of the description."""
    words = re.findall(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]{5,}", f"{lead.description} {lead.name}")
    seen, out = set(), []
    for w in sorted(words, key=len, reverse=True):
        key = w.lower()
        if key not in STOPWORDS and key not in seen:
            seen.add(key)
            out.append(w)
    return out[:limit]


def parse_catalogue(text: str) -> dict | None:
    """Labelled Förderkatalog text from step 1 -> facts (fkz, programme, thema, recipient, executing, start, end,
    amount_eur, lines).

    Supports the multi-line format ("Förderkennzeichen: 03EFBW0275" per line) and the older one-line
    format ("FKZ 03EFBW0275; Programm: ...; Laufzeit: 01.09.2024–30.09.2026; Summe: 972.638,00 €").
    Person names in topic, recipient and executing unit are removed (`context.text.strip_persons`); a
    topic, recipient or executing unit that is only a person or step 1's "?" is dropped (no fact, no line).
    Returns None unless an FKZ and at least one further label are present.
    """
    facts, lines = {}, []
    for part in re.split(r"\n|;\s+", text or ""):
        part = " ".join(part.split())
        for key, labels in CATALOGUE_LABELS.items():
            match = re.fullmatch(rf"(?:{labels})\s*:?\s+(.+)|(?:{labels})\s*:\s*(.+)", part, re.IGNORECASE)
            if match and key not in facts:
                value = (match[1] or match[2]).strip()
                if key in ("thema", "recipient", "executing"):
                    value, part = strip_persons(value), strip_persons(part)
                    if value.startswith("?"):       # step 1 writes "?" for an unknown or removed value
                        value = ""
                facts[key] = value or None
                if value:
                    lines.append(part)
                break
    fkz = re.fullmatch(r"[0-9]{2}[A-Z0-9]{4,12}", (facts.get("fkz") or "").strip(" ."))
    if not fkz or len(facts) < 2:
        return None
    out = {"fkz": fkz[0], "programme": facts.get("programme"), "thema": facts.get("thema"),
           "recipient": facts.get("recipient"), "executing": facts.get("executing"),
           "start": None, "end": None, "amount_eur": None, "lines": lines}
    days = re.findall(GERMAN_DATE, facts.get("period", ""))
    try:
        if days:
            out["start"] = german_date(days[0])
        if len(days) > 1:
            out["end"] = german_date(days[1])
    except ValueError:
        out["start"] = out["end"] = None
    money = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?\s*(?:EUR|€|Euro)", facts.get("amount", ""))
    if money:
        out["amount_eur"] = int(money[1].replace(".", ""))
    return out


def catalogue_grant(signal: SourceSignal) -> tuple[Grant, Evidence, dict] | None:
    """A Grant plus its Evidence built from a step-1 catalogue signal; no network involved."""
    facts = parse_catalogue(signal.evidence) if signal.type in CATALOGUE_TYPES else None
    if facts is None:
        return None
    from context.foekat import programme_for
    programme = facts["programme"] or programme_for(facts["fkz"], "") or SOURCE_FOEKAT
    grant = Grant(programme=programme, reference=facts["fkz"], recipient=facts["recipient"],
                  amount_eur=facts["amount_eur"], start=facts["start"], end=facts["end"], url=signal.url)
    evidence = Evidence(field="grants", url=signal.url, finding="\n".join(facts["lines"])[:MAX_FINDING],
                        source=SOURCE_FOEKAT, source_date=facts["start"])
    return grant, evidence, facts


def mention_only(signal: SourceSignal) -> bool:
    """A press round-up that names the lead once (idw "Erwähnung") is context, not a dated signal of the lead."""
    return signal.source.startswith(SOURCE_IDW_MENTION)


def default_lookups(cache=_DEFAULT_CACHE, model: str | None = None, patents: bool = False, match: bool = True,
                    match_threshold: float | None = None) -> dict:
    """The live lookups. Each entry is a callable; missing modules are skipped with an error entry.

    `cache`: omitted -> the shared on-disk cache `Cache()` (.cache/context.db or $CONTEXT_CACHE), which is what
    pipeline.py uses; the CLI passes `Cache(--cache)`. `None` -> `NoCache()`, nothing touches the disk.
    Google Patents is off by default: it blocks the IP after about a dozen requests and university
    projects file under the university anyway. Enable it per run with `patents=True` (CLI: --patents).
    `match=False` (CLI: --no-match) skips the project-name -> website matcher (context/website_match.py);
    `match_threshold` overrides its confidence threshold.
    """
    from context.cache import Cache, NoCache
    if cache is _DEFAULT_CACHE:
        cache = Cache()
    elif cache is None:
        cache = NoCache()
    found = {"cache": cache, "model": model}
    for name, module, func in (("imprint", "context.imprint", "imprint_lookup"), ("grants", "context.foekat", "grant_lookup"),
                               ("web_history", "context.wayback", "web_history_lookup"), ("classify", "context.classify", "classify_texts"),
                               ("author", "context.openalex", "author_lookup"), ("idw", "context.idw", "idw_lookup"),
                               ("patents", "context.patents", "patent_lookup"),
                               ("website_match", "context.website_match", "match_lookup"),
                               ("databases", "context.dbsearch", "database_lookup"),
                               ("team", "context.team", "team_lookup")):
        if (name == "patents" and not patents) or (name == "website_match" and not match):
            found[name] = None
            continue
        try:
            found[name] = getattr(__import__(module, fromlist=[func]), func)
            if name == "website_match" and match_threshold is not None:
                found[name] = partial(found[name], threshold=match_threshold)
        except (ImportError, AttributeError) as exc:
            found[name] = None
            logger.warning("Lookup %s nicht verfügbar: %s", name, exc)
    return found


def cached_quotes(extract_quotes: Callable, cache, model=None) -> Callable:
    """Memoise the Ollama quote extractor (context/ollama.py) in the shared cache so a second run yields the same quotes.

    Persistent layer on top of the in-process `lru_cache` of `context.ollama.request_quotes`, see context/cache.py.
    The key covers the model and the full signals; hits refer to signals by index, so two signals with the same URL
    cannot swap quotes (Leonard, 032f20d).
    """
    def wrapped(name, signals, fields):
        payload = [model, name, sorted(fields), [signal.model_dump(mode="json") for signal in signals]]
        key = "quotes:v2:" + hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()
        hit = cache.get(key) if cache is not None else None
        if hit is None:
            indices = {id(signal): index for index, signal in enumerate(signals)}
            hit = [(field, quote, indices[id(signal)])
                   for field, quote, signal in extract_quotes(name, signals, fields) if id(signal) in indices]
            if cache is not None:
                cache.set(key, hit)
        return [(field, quote, signals[index]) for field, quote, index in hit]
    return wrapped


# --- lookups ---------------------------------------------------------------------------------------

def _accepts(func, keyword: str) -> bool:
    """True if the lookup callable takes `keyword` (injected test doubles may predate a new parameter)."""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == keyword or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def _run(lookups: dict, name: str, merged: Lookup, call):
    """Run one lookup; a failing lookup becomes an error entry instead of aborting the lead."""
    func = lookups.get(name)
    if func is None:
        if name not in ("patents", "website_match", "databases", "team"):
            merged.errors.append("%s: Modul nicht verfügbar" % name)
        return None
    try:
        result = call(func)
    except Exception as exc:  # defensive: third-party or network failure must not kill the dossier
        logger.exception("Lookup %s failed", name)
        merged.errors.append("%s: %s" % (name, type(exc).__name__))
        return None
    lookup = result[1] if isinstance(result, tuple) else result
    merged.merge(lookup)
    if not lookup.errors:
        if name not in merged.fields.setdefault("_sources", []):
            merged.fields["_sources"].append(name)
    return result


@dataclass
class _LookupHits:
    """What the lookups return besides the merged Lookup."""
    grants: list[Grant] = dc_field(default_factory=list)
    patents: list = dc_field(default_factory=list)
    profiles: dict[str, FounderProfile] = dc_field(default_factory=dict)
    namesake_urls: set[str] = dc_field(default_factory=set)
    directors: list[str] = dc_field(default_factory=list)      # Impressum managing directors (lead without founders)
    imprint_url: str | None = None
    imprint_text: str = ""
    team: list[FounderProfile] = dc_field(default_factory=list)   # context/team.py
    oa_tech: set[str] = dc_field(default_factory=set)               # names with background 'tech' from OpenAlex


def _run_lookups(lead: RawLead, lookups: dict, signals: list[SourceSignal], offline: list, earliest: date | None,
                 merged: Lookup, website: str | None = None) -> _LookupHits:
    """Imprint, grants, web history, idw, patents and OpenAlex in this order; their texts extend `signals`.

    `website`: the step-1 website or, for a lead without one, the site found by the matcher (`_match_website`).
    """
    hits = _LookupHits()
    cache = lookups.get("cache")
    website = website or (str(lead.website) if lead.website else None)
    grant_institution = next((f["recipient"].split(",")[0].strip() for _, _, f in offline if f["recipient"]), None) or None
    if website:
        _run(lookups, "imprint", merged, lambda f: f(website, cache=cache))
    reference = next((f["fkz"] for _, _, f in offline), None) or next(
        (m.group(0) for s in signals if source_binding(lead, s) is not False
         for m in [re.search(r"(?<![A-Za-z0-9])03E[FG][A-Za-z0-9]{3,}", s.evidence)] if m), None)
    institution = merged.fields.get("institution")
    result = _run(lookups, "grants", merged, lambda f: f(lead.name, institution=grant_institution or institution or lead.location,
                                                         reference=reference, cache=cache))
    if result:
        hits.grants = list(result[0])
    institution = grant_institution or institution or next(
        (re.split(r",| - ", g.recipient)[0].strip() for g in hits.grants if g.recipient), None)
    history_kwargs = {"not_before": earliest} if earliest and _accepts(lookups.get("web_history"), "not_before") else {}
    if (confirmed := _site_confirms_project(signals + merged.signals, website, reference)) and _accepts(lookups.get("web_history"), "site_confirmed"):
        history_kwargs["site_confirmed"] = confirmed
        if not confirmed.startswith("Website nennt FKZ") and _accepts(lookups.get("web_history"), "confirmed_years"):
            history_kwargs["confirmed_years"] = EXIST_CONFIRMED_YEARS    # "EXIST" alone vouches only for a recent domain
    _run(lookups, "web_history", merged, lambda f: f(website, lead.name, cache=cache,
                                                     **history_kwargs))
    _check_databases(lead, lookups, merged, signals, website, offline, cache)
    _run(lookups, "idw", merged, lambda f: f(lead.name, institution=institution, founders=list(lead.founders), cache=cache))
    result = _run(lookups, "patents", merged, lambda f: f(lead.name, list(lead.founders), cache=cache))
    hits.patents = list(result[0]) if result else []
    hits.namesake_urls = _press_namesakes(merged, earliest)
    signals.extend(s for s in merged.signals if str(s.url) not in hits.namesake_urls)
    terms = field_terms(lead)
    for founder in dict.fromkeys(lead.founders):
        result = _run(lookups, "author", merged, lambda f, n=founder: f(n, institution=institution, field_terms=terms, cache=cache))
        if result and result[0] is not None:
            hits.profiles[founder] = result[0]
    # EXIST leads have no founders in step 1; a company's Impressum names its managing directors (usually the
    # founders of a spin-off). They get the same OpenAlex lookup, disambiguated by the catalogue institution.
    if not lead.founders:
        directors = merged.fields.get("managing_directors") or []
        hits.directors = [d for d in dict.fromkeys(directors) if isinstance(d, str) and d.strip()][:MAX_DIRECTOR_LOOKUPS]
        hits.imprint_url = merged.fields.get("imprint_url")
        hits.imprint_text = next((sig.evidence for sig in merged.signals if sig.type == "impressum"), "")
        # No field terms: a catalogue lead's terms are only its project name, which made every count 0 ("0 Papers im
        # Produktfeld") although the person publishes in the field. Without terms works_in_field stays unknown
        # (neutral in scoring) and the lookup costs one OpenAlex call instead of two.
        for director in hits.directors:
            result = _run(lookups, "author", merged, lambda f, n=director: f(n, institution=institution, field_terms=[], cache=cache))
            if result and result[0] is not None:
                hits.profiles[director] = result[0]
    if lookups.get("team"):
        _run_team(lead, lookups, merged, signals, website, hits, institution, cache)
    _openalex_background(hits, merged)
    return hits


def _team_texts(signals: list[SourceSignal], website: str | None, merged: Lookup, cache) -> list[tuple[str, str, str]]:
    """(text, url, origin) already at hand for the team lookup: idw articles, website pages, project pages (cache)."""
    from context.web import FETCH_ERRORS, fetch as web_fetch, site_key
    texts = [(s.evidence, str(s.url), "Presse") for s in signals if s.type == "idw" and not mention_only(s)]
    texts += [(s.evidence, str(s.url), "Website") for s in signals
              if s.type == "website" and website and site_key(str(s.url)) == site_key(website)]
    for url in list(dict.fromkeys(str(e.url) for e in merged.evidence if e.field == "project_page"))[:2]:
        try:
            _, page = web_fetch(url, site_key(url), cache=cache)
        except FETCH_ERRORS:
            continue
        texts.append(("\n".join(page.lines), url, "Presse"))
    return texts


def _run_team(lead: RawLead, lookups: dict, merged: Lookup, signals: list[SourceSignal], website: str | None,
              hits: "_LookupHits", institution: str | None, cache) -> None:
    """Team composition (context/team.py); new persons (max. MAX_TEAM_OPENALEX) get the OpenAlex lookup."""
    known = list(dict.fromkeys(lead.founders)) or list(hits.directors)
    try:
        profiles, found = lookups["team"](lead.name, website=website, location=lead.location, institution=institution,
                                          known_names=known, texts=_team_texts(signals, website, merged, cache), cache=cache)
    except Exception as exc:  # noqa: BLE001 - a failing lookup must not kill the dossier
        logger.exception("Lookup team failed")
        merged.errors.append("team: %s" % type(exc).__name__)
        return
    merged.evidence.extend(found.evidence)
    merged.errors.extend(found.errors)
    hits.team = list(profiles)
    if profiles and "team" not in merged.fields.setdefault("_sources", []):
        merged.fields["_sources"].append("team")
    from context.team import name_key
    known_keys = {name_key(k) for k in known}
    new = [p.name for p in profiles if name_key(p.name) not in known_keys][:MAX_TEAM_OPENALEX]
    for person in new:
        result = _run(lookups, "author", merged, lambda f, n=person: f(n, institution=institution, field_terms=[], cache=cache))
        if result and result[0] is not None:
            hits.profiles[person] = result[0]


def _openalex_background(hits: "_LookupHits", merged: Lookup) -> None:
    """OpenAlex fallback agreed with scorer: >= OPENALEX_TECH_WORKS works -> background 'tech', with its own Evidence."""
    for name, profile in hits.profiles.items():
        if profile.openalex_url and (profile.works_total or 0) >= OPENALEX_TECH_WORKS:
            hits.oa_tech.add(name)
            merged.evidence.append(Evidence(field="founder_profiles", url=profile.openalex_url, source=SOURCE_OPENALEX_LABEL,
                                            finding="%s: background tech aus OpenAlex (%d Arbeiten)" % (name, profile.works_total)))


def _press_namesakes(merged: Lookup, earliest: date | None) -> set[str]:
    """URLs of idw articles from long before the first sourced signal.

    Such an article is about a namesake ("procado Consulting", 2013, for a 2025 EXIST project): it must neither
    date the lead earlier nor feed the classifier.
    """
    urls = set()
    cutoff = years_before(earliest, PRESS_NAMESAKE_YEARS) if earliest else None
    for s in merged.signals:
        if cutoff and s.type == "idw" and s.date is not None and s.date < cutoff:
            urls.add(str(s.url))
            merged.errors.append("idw: Artikel %s vom %s vor erstem Signal, vermutlich Namensvetter" % (s.url, s.date.isoformat()))
    return urls


# --- rule extraction -------------------------------------------------------------------------------

class _Facts:
    """Claims per field, each backed by deduplicated Evidence appended to the dossier's evidence list."""

    def __init__(self, evidence: list[Evidence], is_demo: bool):
        self.evidence = evidence
        self.is_demo = is_demo
        self.claims: defaultdict[str, dict[str, Claim]] = defaultdict(dict)
        self._by_key: dict = {}

    def record(self, field: str, value: str, excerpt: str, signal: SourceSignal, *,
               model_quote: bool = False, sourcing: bool = False) -> Evidence:
        key = (field, signal.url, signal.date, excerpt)
        if key not in self._by_key:
            item = Evidence(field=field, source=signal.source, url=signal.url,
                            source_date=signal.date, finding=excerpt,
                            verification_status=("assumption" if self.is_demo else
                                                 "unverified" if sourcing else "source_matched"))
            self._by_key[key] = item
            self.evidence.append(item)
        item = self._by_key[key]
        claim = self.claims[field].setdefault(value.casefold(), Claim(
            value=value, evidence_ids=[item.evidence_id],
            origin="model_selected_quote" if model_quote else "source_statement",
        ))
        if item.evidence_id not in claim.evidence_ids:
            claim.evidence_ids.append(item.evidence_id)
        return item

    def claim(self, field: str) -> Claim | None:
        """The claim of `field` if exactly one value was found."""
        values = self.claims[field]
        return next(iter(values.values())) if len(values) == 1 else None

    def value(self, field: str) -> str | None:
        claim = self.claim(field)
        return claim.value if claim else None

    def latest_metric(self, metric: str) -> str | None:
        prefix = f"traction.metrics.{metric}."
        latest = max((key for key in self.claims if key.startswith(prefix)), default=None)
        return self.value(latest) if latest else None


def _sourcing_signal(lead: RawLead) -> SourceSignal:
    """The sourcing step itself as a signal, for facts reported by step 1 (has_vc, location, founding date)."""
    return SourceSignal(source=lead.source_name or SOURCE_SOURCING, url=lead.source_url,
                        type="sourcing", evidence=lead.description.strip() or lead.name)


def _extract_rules(facts: _Facts, lead: RawLead, signals: list[SourceSignal], founders: list[str],
                   source: SourceSignal) -> list[Evidence]:
    """Record every rule fact found in the texts; returns the discovery-signal evidence."""
    if lead.has_vc is not None:
        facts.record("vc_status", "confirmed" if lead.has_vc else "reported_none",
                     f"has_vc = {str(lead.has_vc).lower()}", source, sourcing=True)
    if lead.location:
        facts.record("company.reported_location", lead.location, f"Standort laut Sourcing: {lead.location}",
                     source, sourcing=True)
    discovery = []
    for signal in signals:
        if signal in lead.signals:
            item = facts.record("discovery_signals", signal.evidence[:MAX_FINDING], signal.evidence[:MAX_FINDING], signal)
            if item not in discovery:
                discovery.append(item)
        if signal.date is not None and not mention_only(signal):
            facts.record("first_signal_date", signal.date.isoformat(), signal.evidence[:MAX_FINDING], signal)
        for line in statements(signal):
            if len(line) <= MAX_FINDING:
                _record_line(facts, line, signal, founders)
    return discovery


def _record_line(facts: _Facts, line: str, signal: SourceSignal, founders: list[str]) -> None:
    """All label, prose, money, metric, stage, funding and founder rules for one line."""
    record = partial(facts.record, excerpt=line, signal=signal)
    for field, labels in LABELS.items():
        if value := labelled(line, labels):
            record(field, value)
        elif field in PROSE and (match := re.fullmatch(PROSE[field], line, re.IGNORECASE)):
            record(field, match[1])
    for field, labels in RESEARCH_LABELS.items():
        if value := labelled(line, labels):
            if field == "company.founding_date":
                try:
                    if re.fullmatch(GERMAN_DATE, value):
                        value = german_date(value).isoformat()
                    else:
                        value = date.fromisoformat(value.strip(".")).isoformat()
                except ValueError:
                    continue
            record(field, value)
    for field, labels in MONEY_LABELS.items():
        if (value := labelled(line, labels)) and (amount := euros(value)):
            record(field, str(amount))
    _record_metrics(record, line)
    product = labelled(line, PRODUCT_STAGE_LABEL)
    if product and (stage := stage_value(product, PRODUCT_STAGES)):
        record("product_stage", stage)
    elif stage_value(line, {"mvp": r"(?:Unser MVP ist (?:fertig|verfügbar)|Our MVP is (?:ready|available))"}):
        record("product_stage", "mvp")
    funding = labelled(line, FUNDING_STATUS_LABEL)
    if funding and (status := stage_value(funding, FUNDING)):
        record("funding_status", status)
        if status == "vc_backed":
            record("vc_status", "confirmed")
    elif round_match := ROUND_CLOSED.fullmatch(line):
        record("funding_status", "funded")
        record("funding_stage", round_match[1] or round_match[2])
        record("funding.rounds", round_match[1] or round_match[2])
    vc = labelled(line, VC_STATUS_LABEL)
    if vc and stage_value(vc, {"confirmed": r"Ja|Yes|Vorhanden|VC-backed"}):
        record("vc_status", "confirmed")
    if vc and stage_value(vc, {"none": r"Nein|No|Kein VC|No VC"}):
        record("vc_status", "reported_none")
    for index, name in enumerate(founders):
        _record_founder(record, line, index, name)


def _record_metrics(record: Callable, line: str) -> None:
    """'Jahresumsatz 2024: 1,2 Mio. EUR' -> traction.metrics.revenue.2024 = 1200000."""
    for metric, (labels, _, currency) in PERIOD_METRICS.items():
        match = re.fullmatch(rf"(?:{labels})\s+((?:19|20)\d{{2}})\s*:\s*(.+)", line, re.IGNORECASE)
        if match is None:
            continue
        number = euros(match[2]) if currency else None
        if metric == "customer_count" and re.fullmatch(r"\d{1,12}", match[2]):
            number = int(match[2])
        if metric == "revenue_growth" and re.fullmatch(r"[+-]?\d{1,5}(?:[.,]\d{1,3})?\s*%", match[2]):
            number = Decimal(match[2].removesuffix("%").strip().replace(",", "."))
        if number is not None:
            record(f"traction.metrics.{metric}.{match[1]}", format(Decimal(number).normalize(), "f"))


def _record_founder(record: Callable, line: str, index: int, name: str) -> None:
    """'Kim Muster - Rolle: CTO', 'Kim Muster | CEO', 'Kim Muster promovierte in ...'."""
    person = re.escape(" ".join(name.split()))
    for field, label in FOUNDER_FIELDS.items():
        if value := labelled(line, rf"{person}\s+[\-–]\s+(?:{label})"):
            record(f"founder_profiles.{index}.{field}", value)
    role = re.fullmatch(rf"{person}\s*(?:\||[–—-]|,\s)\s*{FOUNDER_ROLE}", line, re.IGNORECASE)
    if role:
        record(f"founder_profiles.{index}.role", role[1])
    background = re.fullmatch(rf"{person}\s+(?:promovierte in|studierte|has a PhD in|studied)\s+.+", line, re.IGNORECASE)
    if background:
        record(f"founder_profiles.{index}.qualifications", line)


# --- classifier and model quotes -------------------------------------------------------------------

def _classify(lead: RawLead, lookups: dict, signals: list[SourceSignal], merged: Lookup, facts: _Facts,
              exclude_names: list[str]) -> None:
    """Run the text classifier over the real excerpts; rule facts win over its product_stage."""
    before = len(merged.evidence)
    # Sourcing's own one-line summaries are not company statements; only real excerpts are classified.
    summaries = {id(s) for s in lead.signals if len(s.evidence) < SUMMARY_CHARS}
    texts = [s for s in signals if id(s) not in summaries]
    classify_kwargs = {"exclude_names": exclude_names} if exclude_names and _accepts(lookups.get("classify"), "exclude_names") else {}
    _run(lookups, "classify", merged, lambda f: f(lead.name, texts, model=lookups.get("model"), cache=lookups.get("cache"),
                                                   founders=list(lead.founders), **classify_kwargs))
    facts.evidence.extend(merged.evidence[before:])
    if facts.claims["product_stage"] and "product_stage" in merged.fields:
        del merged.fields["product_stage"]


def _model_quotes(facts: _Facts, lead: RawLead, signals: list[SourceSignal], extract_quotes: Callable,
                  merged: Lookup) -> bool:
    """Ask the quote extractor for text fields the rules left empty; True if the model call failed."""
    text_fields = [*LABELS, *(f"product.{field}" for field in PRODUCT_FIELDS)]
    missing = tuple(field for field in text_fields if field != "funding_stage" and not facts.claims[field])
    # Only the company's own statements and press texts are quotable.
    quotable = [s for s in signals if s.type not in UNQUOTABLE_TYPES and "for sale" not in s.evidence.lower()]
    if not (missing and quotable):
        return False
    try:
        model_signals = [signal.model_copy(deep=True) for signal in quotable]
        for field, quote, signal in extract_quotes(lead.name, model_signals, missing):
            if field in missing and signal in quotable and quote.strip() and quote in signal.evidence:
                quoted = SourceSignal(source=MODEL_QUOTE_PREFIX + signal.source, type=signal.type,
                                      url=signal.url, date=signal.date, evidence=signal.evidence)
                facts.record(field, quote, quote, quoted, model_quote=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Ollama-Zitate für %s fehlgeschlagen", lead.id, exc_info=True)
        merged.errors.append("ollama: %s" % type(exc).__name__)
        return True
    return False


# --- derived statuses ------------------------------------------------------------------------------

def _funding_status(facts: _Facts, grants: list[Grant]) -> tuple[str, str]:
    """(vc_status, funding_status) from the recorded claims; a documented grant counts as non-VC funding."""
    vc_status = facts.value("vc_status") or ("conflicting" if facts.claims["vc_status"] else "unknown")
    funding_facts = set(facts.claims["funding_status"])
    if vc_status in {"confirmed", "conflicting"}:
        funding_facts.add("vc_backed")
    if len(funding_facts) > 1:
        funding_facts.discard("funded")
    if "vc_backed" in funding_facts:
        funding_facts.discard("non_vc_funded")
    funding_status = (next(iter(funding_facts)) if len(funding_facts) == 1
                      else "conflicting" if funding_facts else "unknown")
    if funding_status == "unknown" and grants and vc_status in {"reported_none", "unknown"}:
        funding_status = "non_vc_funded"  # a public grant is documented funding without VC involvement
    return vc_status, funding_status


def _open_questions(facts: _Facts, founders: list[str], vc_status: str, merged: Lookup, model_failed: bool) -> list[str]:
    """Research questions for the gaps the rules, the classifier and the model left."""
    questions = [question for field, question in QUESTIONS.items() if facts.value(field) is None]
    if vc_status in {"conflicting", "unknown"}:
        questions.append("Welche Investoren sind bereits beteiligt?")
    if facts.value("product_stage") is None and not merged.fields.get("product_stage"):
        questions.append("Welcher Produktstand ist heute nachweisbar?")
    if not founders or any(
        facts.value(f"founder_profiles.{i}.{field}") is None
        for i in range(len(founders)) for field in ("role", "qualifications")
    ):
        questions.append("Wer gehört zum Gründungsteam und wer bringt welche Erfahrung mit?")
    if model_failed:
        questions.append("Welche offenen Angaben lassen sich anhand der Originalquellen bestätigen?")
    if not facts.claim("customer_problem"):
        questions.append("Welches konkrete Kundenproblem löst ihr?")
    if not facts.claim("target_customers"):
        questions.append("Welche Kundengruppe nutzt das Produkt?")
    return questions


def _founding(facts: _Facts, lead: RawLead, source: SourceSignal, questions: list[str]) -> tuple[Claim | None, str]:
    """(founding claim, status): documented by a source, reported by sourcing, conflicting or unknown."""
    founding_claim = facts.claim("company.founding_date")
    founding_status = "documented" if founding_claim else "unknown"
    if lead.founding_year:
        raw_date = f"{lead.founding_year:04}"
        if lead.founding_month:
            raw_date += f"-{lead.founding_month:02}"
        facts.record("company.reported_founding_date", raw_date, f"Gründung laut Sourcing: {raw_date}",
                     source, sourcing=True)
        if founding_claim is None:
            founding_claim = facts.claim("company.reported_founding_date")
            founding_status = "reported"
        elif not founding_claim.value.startswith(raw_date):
            founding_status = "conflicting"
    if len(facts.claims["company.founding_date"]) > 1:
        founding_status = "conflicting"
    if founding_status == "conflicting":
        founding_claim = None
        questions.append("Wann und in welcher Rechtsform wurde das Unternehmen gegründet?")
    return founding_claim, founding_status


def _reported_metrics(facts: _Facts, is_demo: bool) -> dict[str, list[MarketMeasure]]:
    """Unambiguous yearly company metrics (revenue, growth, customers) as MarketMeasure lists."""
    reported = defaultdict(list)
    for field in sorted(key for key in facts.claims if key.startswith("traction.metrics.")):
        if claim := facts.claim(field):
            _, _, metric, year = field.split(".")
            _, unit, currency = PERIOD_METRICS[metric]
            reported[metric].append(MarketMeasure(
                value=float(claim.value), unit=unit, currency=currency, geography="Unternehmensebene",
                period=Period(start_year=int(year), end_year=int(year)),
                methodology="Explizit veröffentlichte Jahresangabe des Unternehmens oder der Fundquelle",
                data_type="assumption" if is_demo else "observed", evidence_ids=claim.evidence_ids,
            ))
    return dict(reported)


def _context_v2(facts: _Facts, lead: RawLead, founders: list[str], founding: tuple[Claim | None, str],
                statuses: tuple[str, str], round_terms: dict, discovery: list[Evidence], light: bool,
                questions: list[str]) -> ContextV2:
    """Assemble the structured research record from the claims."""
    founding_claim, founding_status = founding
    vc_status, funding_status = statuses
    claim_for = facts.claim
    return ContextV2(
        company=CompanyResearch(
            founding_date=founding_claim, founding_date_status=founding_status,
            headquarters=claim_for("company.headquarters"),
            reported_location=claim_for("company.reported_location"),
            germany_evidence_ids=[lead.country_evidence.evidence_id] if lead.country_evidence else [],
            company_status=claim_for("company.company_status"),
        ),
        founders=[
            FounderResearch(name=name, **{
                field: claim_for(f"founder_profiles.{index}.{field}") for field in FOUNDER_FIELDS
            })
            for index, name in enumerate(founders)
        ],
        product=ProductResearch(
            **{field: claim_for(field) for field in ("customer_problem", "solution", "target_customers", "technology")},
            **{field: claim_for(f"product.{field}") for field in PRODUCT_FIELDS},
            maturity=claim_for("product_stage"),
        ),
        traction=TractionResearch(
            **{field: list(facts.claims[f"traction.{field}"].values()) for field in TRACTION_EVENTS},
            **{field: claim_for(f"traction.{field}") for field in TRACTION_METRICS},
            reported_metrics=_reported_metrics(facts, lead.is_demo),
        ),
        funding=FundingResearch(
            status=funding_status, vc_status=vc_status, capital_need=claim_for("capital_need"),
            status_evidence_ids=list(dict.fromkeys(
                evidence_id for field in ("funding_status", "vc_status")
                for claim in facts.claims[field].values() for evidence_id in claim.evidence_ids
            )),
            **{field: list(facts.claims[f"funding.{field}"].values()) for field in FUNDING_EVENTS},
            **{field: claim_for(f"funding.{field}") for field in FUNDING_FIELDS},
            **round_terms,
            round_terms_evidence_ids=[
                evidence_id for field in MONEY_LABELS if (claim := claim_for(field))
                for evidence_id in claim.evidence_ids
            ],
        ),
        discovery_signals=discovery,
        research_status=ResearchStatus(mode="light" if light else "standard", gaps=questions),
    )


def _founding_year_hint(lead: RawLead, merged: Lookup, evidence: list[Evidence], earliest: date | None) -> int | None:
    """A plausible founding year from idw: the lookup's hint, else the date of an article that says 'gegründet'."""
    def plausible(year: int) -> bool:
        """A project that started under EXIST in 2025 was not founded in 2013: reject hints long before it."""
        if earliest and year < earliest.year - PRESS_NAMESAKE_YEARS:
            message = "idw: Gründungsjahr %d verworfen (vor erstem Signal)" % year
            if message not in merged.errors:
                merged.errors.append(message)
            return False
        return True

    hint = merged.fields.get("founding_year_hint")
    if isinstance(hint, int) and not plausible(hint):
        hint = None
    if not isinstance(hint, int):  # "X wurde gegründet" without a year: the article date bounds the founding year
        lead_re = name_pattern(lead.name)       # umlaut-folded, legal form stripped, whole word
        articles = {str(s.url): s for s in merged.signals if s.type == "idw"}

        def about_lead(url) -> bool:
            article = articles.get(str(url))
            if article is None or lead_re is None:
                return False
            title = article.evidence.split("\n", 1)[0]
            return bool(lead_re.search(idw_fold(title))) or len(lead_re.findall(idw_fold(article.evidence))) >= 2

        for e in merged.evidence:
            if (e.field == "founding_statement" and e.source_date and lead_re is not None and lead_re.search(idw_fold(e.finding))
                    and FOUNDING_WORDS.search(e.finding) and not FOUNDING_PLANNED.search(e.finding)
                    and about_lead(e.url) and plausible(e.source_date.year)):
                hint = e.source_date.year
                evidence.append(Evidence(field="founding_year_mention", url=e.url, finding=e.finding, source=e.source,
                                         source_date=e.source_date))
                break
    return hint if isinstance(hint, int) and 1900 <= hint <= 2100 else None


def _founder_profiles(facts: _Facts, founders: list[str], profiles: dict[str, FounderProfile]) -> list[FounderProfile]:
    """OpenAlex profile (if any) per founder, with role and qualifications from the rule claims."""
    out = []
    for index, name in enumerate(founders):
        base = profiles.get(name)
        values = base.model_dump() if base else {"name": name}
        values["role"] = facts.value(f"founder_profiles.{index}.role")
        values["qualifications"] = facts.value(f"founder_profiles.{index}.qualifications") or values.get("qualifications")
        out.append(FounderProfile(**values))
    return out


IMPRINT_ROLE = re.compile(r"\(\s*(Project Lead(?:er)?|Projektleit(?:er|erin|ung)|Teamleit(?:er|erin|ung)|Team Lead|"
                          r"Principal Investigator|CEO|CTO|COO|CFO|Gründer(?:in)?|Co-?Founder|Founder)\b", re.IGNORECASE)


def _imprint_role(name: str, text: str) -> str:
    """'Dr. Elisha Krieg (Project Leader, EXIST EFT Project)' -> 'Project Leader (Impressum)'; default: managing director."""
    surname = name.split()[-1] if name.split() else name
    match = re.search(re.escape(surname) + r"\s*" + IMPRINT_ROLE.pattern, text or "", re.IGNORECASE)
    return "%s (Impressum)" % match[1] if match else DIRECTOR_ROLE


def _director_profiles(hits: _LookupHits) -> list[FounderProfile]:
    """Managing directors from the Impressum as team profiles: OpenAlex data if matched, source = Impressum URL."""
    out = []
    for name in hits.directors:
        base = hits.profiles.get(name)
        values = base.model_dump() if base else {"name": name}
        values["role"] = _imprint_role(name, hits.imprint_text)
        values["source_url"] = values.get("source_url") or hits.imprint_url
        out.append(FounderProfile(**values))
    return out


def _team_profiles(base: list[FounderProfile], hits: "_LookupHits") -> list[FounderProfile]:
    """Merge the team lookup into founder/Impressum profiles by name; add new persons; OpenAlex data and fallback."""
    from context.team import name_key
    out = [p.model_copy() for p in base]
    index = {name_key(p.name): i for i, p in enumerate(out)}
    for t in hits.team:
        key = name_key(t.name)
        if key in index:
            p = out[index[key]]
            roles = [r for r in (p.role or "").split("; ") if r]
            if not t.role.startswith("Teammitglied") or not roles:
                roles += [r for r in t.role.split("; ") if r not in roles]
            out[index[key]] = p.model_copy(update={"role": "; ".join(roles) or None, "background": p.background or t.background,
                                                   "institution": p.institution or t.institution})
            continue
        values = t.model_dump()
        if (oa := hits.profiles.get(t.name)) is not None:
            values.update({k: getattr(oa, k) for k in ("openalex_url", "works_total", "works_in_field", "match_confidence")})
            values["institution"] = values.get("institution") or oa.institution
        index[key] = len(out)
        out.append(FounderProfile(**values))
    return [p.model_copy(update={"background": "tech"}) if p.background is None and p.name in hits.oa_tech else p for p in out]


def _lookup_questions(questions: list[str], extra: dict) -> list[str]:
    """Adjust the questions to what the lookups found (grant covers capital need; legal form, IP, partners)."""
    questions = [q for q in questions if not (q.startswith("Welchen Kapitalbedarf") and extra.get("grants"))]
    if "legal_form" not in extra:
        questions.append("Welche Rechtsform hat das Vorhaben heute (Impressum nicht gefunden)?")
    if "ip_status" not in extra:
        questions.append("Gibt es Schutzrechte oder Patentanmeldungen?")
    if not extra.get("partners"):
        questions.append("Welche Piloten, Design-Partner oder Absichtserklärungen gibt es?")
    return questions


def _match_website(lead: RawLead, lookups: dict, offline: list, merged: Lookup) -> str | None:
    """Project name -> company website for a lead without step-1 website (context/website_match.py).

    Runs before Impressum, Wayback and OpenAlex so that they can use the site. The Lookup (matched_website,
    match_confidence, project_page evidence) is merged first, so its match_confidence wins over the
    Förderkatalog's project match. Returns the website only when the matcher set one (confidence >= threshold).
    """
    if lead.website or lead.is_demo or not lookups.get("website_match"):
        return None
    from context.website_match import lead_context
    facts = offline[0][2] if offline else {}
    result = _run(lookups, "website_match", merged, lambda f: f(lead.name, cache=lookups.get("cache"), **lead_context(lead, facts)))
    lookup = result[1] if isinstance(result, tuple) else result
    return (lookup.fields.get("matched_website") if lookup is not None else None) or None


def _check_databases(lead: RawLead, lookups: dict, merged: Lookup, signals: list[SourceSignal], website: str | None,
                     offline: list, cache) -> None:
    """Startup-database search (context/dbsearch.py) after Wayback; it decides `in_databases` where it ran.

    A confirmed live profile sets True (and adds its URLs); a search without profile sets False unless Wayback found
    an archived profile. Its Evidence goes first, so the scorer reads the real search, not the Wayback CDX query.
    """
    if not lookups.get("databases"):
        return
    from context.web import site_key
    facts = offline[0][2] if offline else {}
    text = "\n".join(s.evidence for s in signals if s.type == "website" and website and site_key(str(s.url)) == site_key(website))
    db = Lookup()
    try:
        db = lookups["databases"](lead.name, website=website, location=lead.location,
                                  institution=facts.get("executing") or facts.get("recipient"), website_text=text, cache=cache)
    except Exception as exc:  # noqa: BLE001 - a failing lookup must not kill the dossier
        logger.exception("Lookup databases failed")
        merged.errors.append("databases: %s" % type(exc).__name__)
        return
    merged.errors.extend(db.errors)
    found = db.fields.get("in_databases")
    if found is None:
        return
    if found is True or merged.fields.get("in_databases") is not True:
        merged.fields["in_databases"] = found
        if found:
            merged.fields["database_urls"] = list(dict.fromkeys([*db.fields.get("database_urls", []),
                                                                 *map(str, merged.fields.get("database_urls") or [])]))
        merged.evidence[:0] = db.evidence
    else:
        merged.evidence.extend(db.evidence)
    if "databases" not in merged.fields.setdefault("_sources", []):
        merged.fields["_sources"].append("databases")


def _site_confirms_project(signals: list[SourceSignal], website: str | None, reference: str | None) -> str | None:
    """'Website nennt FKZ …' / 'Website nennt EXIST' when the loaded company pages name the project's funding."""
    from context.web import site_key
    if not website:
        return None
    text = "\n".join(s.evidence for s in signals if s.type in ("website", "impressum") and site_key(str(s.url)) == site_key(website))
    if reference and re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(reference), text, re.IGNORECASE):
        return "Website nennt FKZ %s" % reference
    if re.search(r"\bEXIST\b", text):
        return "Website nennt EXIST"
    return None


def _website_text(signals: list[SourceSignal], website: str | None) -> Evidence | None:
    """Cleaned text of the loaded company pages as Evidence field="website_text" (noise filter in scoring)."""
    from context.web import site_key
    pages = [s for s in signals if s.type == "website" and website and site_key(str(s.url)) == site_key(website)]
    if not pages:
        return None
    text = "\n".join(s.evidence for s in pages)[:WEBSITE_TEXT_CHARS]
    return Evidence(field="website_text", url=pages[0].url, finding=text, source=pages[0].source,
                    verification_status="source_matched")


def _collect_signals(lead: RawLead, load_pages: Callable, load_original: Callable | None, light: bool,
                     website: str | None = None) -> list[SourceSignal]:
    """The lead's signals plus its website pages and the original source page (not for demo or light leads).

    `website` is a matched site (lead without step-1 website); its pages are bound to the lead (`subject_lead_id`),
    because the matcher verified that the site names the project.
    """
    signals = list(lead.signals)
    if lead.website and not lead.is_demo and not light:
        signals.extend(load_pages(str(lead.website)))
    elif website and not lead.is_demo and not light:
        signals.extend(s.model_copy(update={"subject_lead_id": lead.id}) for s in load_pages(website))
    if (load_original and not lead.is_demo and not light
            and not any(signal.url == lead.source_url for signal in signals)):
        if original := load_original(str(lead.source_url)):
            signals.append(original)
    return signals


# --- entry point -----------------------------------------------------------------------------------

def enrich(
    lead: RawLead, *, load_pages: Callable[[str], Iterable[SourceSignal]] = company_pages,
    load_original: Callable[[str], SourceSignal | None] | None = None,
    extract_quotes: Callable | None = None,
    light: bool = False, lookups: dict | None = None,
    as_of: date | None = None,
) -> EnrichedLead:
    """Return the original lead plus public context and per-field evidence.

    `light` uses only the delivered signals (no pages, lookups or model). `lookups` comes from `default_lookups`
    (or test doubles); its "cache" is also used for website pages and model quotes. `as_of` is the scoring date
    (default: `lead.screening_as_of`); signals after it, or bound to another company (`source_binding`), are kept
    only in `scoring_sources` for replay, not used for the facts.
    """
    as_of = as_of or lead.screening_as_of
    if light:
        lookups = None  # light mode never calls external services
    page_cache = lookups.get("cache") if lookups else None
    if page_cache is not None and load_pages is company_pages:
        load_pages = partial(company_pages, cache=page_cache)
    if page_cache is not None and load_original is not None and getattr(load_original, "__name__", "") == "original_page":
        load_original = partial(load_original, cache=page_cache)
    merged = Lookup()
    # Earliest dated sourcing signal (e.g. the EXIST project start): bounds namesake hits from the lookups.
    earliest = min((s.date for s in lead.signals if s.date is not None), default=None)
    # Step 1 delivers the catalogue row as labelled text: the grant is documented without any lookup (also --light).
    offline = [hit for s in lead.signals if not lead.is_demo and (hit := catalogue_grant(s))]
    exclude_names = [text for _, _, f in offline for text in (f["recipient"], f["executing"]) if text]
    matched = _match_website(lead, lookups, offline, merged) if lookups else None
    website = str(lead.website) if lead.website else matched
    signals = _collect_signals(lead, load_pages, load_original, light, website=matched)
    hits = (_run_lookups(lead, lookups, signals, offline, earliest, merged, website=website)
            if lookups and not lead.is_demo else _LookupHits())
    known = {g.reference for g in hits.grants if g.reference}
    grants = hits.grants + [g for g, _, _ in offline if not g.reference or g.reference not in known]   # looked-up grant wins
    evidence = [e for e in merged.evidence if str(e.url) not in hits.namesake_urls] + [e for _, e, _ in offline]
    # Field evidence delivered by a screening export (sourcing/engine.ScreeningReport), deduplicated by id.
    known_ids = {e.evidence_id for e in evidence}
    evidence += list({e.evidence_id: e for entries in lead.field_evidence.values() for e in entries
                      if e.evidence_id not in known_ids}.values())
    if not lead.is_demo and not light and (page_text := _website_text(signals, website)):
        evidence.append(page_text)
    # Frozen source excerpts for the replayable scoring handoff, incl. lookup texts (Impressum, idw, Förderkatalog).
    scoring_sources = [signal.model_copy(deep=True) for signal in signals] if not lead.is_demo else None
    signals = [s for s in signals if source_binding(lead, s) is not False
               and (as_of is None or s.date is None or s.date <= as_of)]

    facts = _Facts(evidence, lead.is_demo)
    source = _sourcing_signal(lead)
    founders = list(dict.fromkeys(lead.founders))
    discovery = _extract_rules(facts, lead, signals, founders, source)
    if lookups and not lead.is_demo and lookups.get("classify"):
        _classify(lead, lookups, signals, merged, facts, exclude_names)
    if extract_quotes and lookups and lookups.get("cache") is not None:
        extract_quotes = cached_quotes(extract_quotes, lookups["cache"], model=lookups.get("model"))
    model_failed = _model_quotes(facts, lead, signals, extract_quotes, merged) if extract_quotes and not light else False

    statuses = _funding_status(facts, grants)
    questions = _open_questions(facts, founders, statuses[0], merged, model_failed)
    founding = _founding(facts, lead, source, questions)
    round_terms = {field: int(value) if (value := facts.value(field)) else None for field in MONEY_LABELS}
    context = _context_v2(facts, lead, founders, founding, statuses, round_terms, discovery, light, questions)

    extra = {k: v for k, v in merged.fields.items() if k in EnrichedLead.model_fields and k not in RawLead.model_fields
             and k not in OWN_FIELDS and k != "founding_year_hint"}   # the hint is set only after the plausibility checks
    if grants:
        extra["grants"] = grants
    if merged.fields.get("contact_email") and not lead.contact_email:
        extra["imprint_email"] = merged.fields["contact_email"]
    if (hint := _founding_year_hint(lead, merged, evidence, earliest)) is not None:
        extra["founding_year_hint"] = hint
    patents = hits.patents + [x for x in merged.fields.get("patents", []) if x not in hits.patents]
    if patents:
        extra["patents"] = patents
    if lookups and not lead.is_demo:
        questions = _lookup_questions(questions, extra)
    founding_claim, founding_status = founding
    revenue = facts.latest_metric("revenue")
    customers = facts.latest_metric("customer_count")
    values = dict(
        evidence=evidence,
        context_v2=context,
        scoring_sources=scoring_sources,
        founder_profiles=_team_profiles(_founder_profiles(facts, founders, hits.profiles) + _director_profiles(hits), hits),
        **{field: facts.value(field) for field in LABELS},
        **round_terms,
        research_questions=questions,
        product_stage=facts.value("product_stage") or merged.fields.get("product_stage"),
        funding_status=statuses[1],
        vc_status=statuses[0],
        first_signal_date=lead.first_signal_date or min((signal.date for signal in signals if signal.date is not None and not mention_only(signal)),
                              default=None),
        founded_on=date.fromisoformat(founding_claim.value) if founding_status == "documented" else None,
        annual_revenue_eur=float(revenue) if revenue is not None else None,
        customer_count=int(customers) if customers is not None else None,
        enrichment_sources=merged.fields.pop("_sources", []),
        enrichment_errors=merged.errors,
    )
    values.update({k: v for k, v in extra.items() if k not in values})
    enriched = EnrichedLead(**lead.model_dump(exclude={"first_signal_date"}), **values)
    if not lead.is_demo:
        enriched.scoring_input = build_scoring_input(enriched, as_of=as_of)
    return enriched
