"""Extract evidenced facts from sourcing signals and public company pages.

Two layers:
1. Rule extraction over all collected texts (this file, label/value patterns, no network).
2. Optional lookups against fixed public sources (Impressum, Förderkatalog, OpenAlex, Wayback)
   and the local Ollama classifier, see context/ENRICHMENT.md. They run only when `lookups`
   is passed (CLI: default on, `--offline` off), so unit tests stay offline.
"""
import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime
from decimal import Decimal
from functools import partial

from context.company import (
    COMPANY_FIELDS, FOUNDER_FIELDS, FUNDING_EVENTS, FUNDING_FIELDS, PRODUCT_FIELDS,
    RESEARCH_LABELS, TRACTION_EVENTS, TRACTION_METRICS,
)
from context.lookup import Lookup
from context.web import company_pages
from context.idw import MENTION_SOURCE, fold as idw_fold, name_pattern
from models import EnrichedLead, Evidence, FounderProfile, Grant, RawLead, SourceSignal
from research_models import (
    Claim, CompanyResearch, ContextV2, FounderResearch, FundingResearch, MarketMeasure, Period,
    ProductResearch, ResearchStatus, TractionResearch,
)
from scoring_input import build_scoring_input

logger = logging.getLogger(__name__)
STOPWORDS = set("""für mit und oder der die das des dem den ein eine einer eines einem einen von zur zum auf aus bei nach über unter durch
ohne gegen sowie auch nicht sind wird werden wurde kann können soll sollen haben hat ist sein ihre ihrer seine seiner unsere unser
entwickelt entwickeln bietet bieten ermöglicht basierend neue neuen neuer innovative innovativ lösung lösungen plattform software system
systeme technologie unternehmen startup start-up produkt produkte kunden projekt the and for with from that this into using based
develops developing provides solution solutions platform company customers product products technology
förderempfänger bundesanteil ausführende stelle förderkennzeichen laufzeit projekt exist-gründungsstipendium-projekt
forschungstransfer gründungsstipendium fkz exist-forschungstransfer exist-gründungsstipendium fördersumme
öffentliche förderung programm thema""".split())
CATALOGUE_TYPES = {"exist_projekt", "foerderprojekt"}
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


def euros(text):
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


def stage_value(text, choices):
    for value, pattern in choices.items():
        if re.fullmatch(pattern, text.strip(" ."), re.IGNORECASE):
            return value
    return None


HEADINGS = "|".join(LABELS.values())


def labelled(line, labels):
    match = re.fullmatch(rf"(?:{labels})\s*[:–]\s*(.+)", line, re.IGNORECASE)
    if not match:
        return None
    value = match[1].strip()
    # Navigation menus produce "Technology: Technology" or "Technology: Projects Knowledge base"; a value that is
    # itself a heading word, or a short capitalised word list without a verb-like token, is not a statement.
    if re.fullmatch(rf"(?:{HEADINGS})", value, re.IGNORECASE):
        return None
    words = value.split()
    if 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words) and not value.endswith((".", "!")):
        return None
    return value


def statements(signal):
    """Treat a text block as a heading/value pair only for recognized labels."""
    lines = [" ".join(line.split()) for line in signal.evidence.splitlines() if line.strip()]
    headings = "|".join([*LABELS.values(), *MONEY_LABELS.values(), *RESEARCH_LABELS.values(),
                         "Produktreife|Produktstatus|Product stage",
                         "Finanzierungsstatus|Funding status|VC-Status|VC status"])
    for i, line in enumerate(lines):
        yield line
        if (i + 1 < len(lines) and re.fullmatch(headings, line, re.IGNORECASE)
                and not re.fullmatch(headings, lines[i + 1], re.IGNORECASE)):
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
    """Labelled Förderkatalog text from step 1 -> facts (fkz, programme, recipient, executing, start, end, amount_eur, lines).

    Supports the multi-line format ("Förderkennzeichen: 03EFBW0275" per line) and the older one-line
    format ("FKZ 03EFBW0275; Programm: ...; Laufzeit: 01.09.2024–30.09.2026; Summe: 972.638,00 €").
    Returns None unless an FKZ and at least one further label are present.
    """
    facts, lines = {}, []
    for part in re.split(r"\n|;\s+", text or ""):
        part = " ".join(part.split())
        for key, labels in CATALOGUE_LABELS.items():
            match = re.fullmatch(rf"(?:{labels})\s*:?\s+(.+)|(?:{labels})\s*:\s*(.+)", part, re.IGNORECASE)
            if match and key not in facts:
                facts[key] = (match[1] or match[2]).strip()
                lines.append(part)
                break
    fkz = re.fullmatch(r"[0-9]{2}[A-Z0-9]{4,12}", (facts.get("fkz") or "").strip(" ."))
    if not fkz or len(facts) < 2:
        return None
    out = {"fkz": fkz[0], "programme": facts.get("programme"), "thema": facts.get("thema"),
           "recipient": facts.get("recipient"), "executing": facts.get("executing"),
           "start": None, "end": None, "amount_eur": None, "lines": lines}
    days = re.findall(r"\d{1,2}\.\d{1,2}\.\d{4}", facts.get("period", ""))
    try:
        if days:
            out["start"] = datetime.strptime(days[0], "%d.%m.%Y").date()
        if len(days) > 1:
            out["end"] = datetime.strptime(days[1], "%d.%m.%Y").date()
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
    programme = facts["programme"] or programme_for(facts["fkz"], "") or "Förderkatalog"
    grant = Grant(programme=programme, reference=facts["fkz"], recipient=facts["recipient"],
                  amount_eur=facts["amount_eur"], start=facts["start"], end=facts["end"], url=signal.url)
    evidence = Evidence(field="grants", url=signal.url, finding="\n".join(facts["lines"])[:1000],
                        source="Förderkatalog", source_date=facts["start"])
    return grant, evidence, facts


def _accepts(func, keyword: str) -> bool:
    """True if the lookup callable takes `keyword` (injected test doubles may predate a new parameter)."""
    import inspect
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == keyword or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def mention_only(signal: SourceSignal) -> bool:
    """A press round-up that names the lead once (idw "Erwähnung") is context, not a dated signal of the lead."""
    return signal.source.startswith(MENTION_SOURCE)


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def default_lookups(cache=None, model: str | None = None, patents: bool = False) -> dict:
    """The live lookups. Each entry is a callable; missing modules are skipped with an error entry.

    Google Patents is off by default: it blocks the IP after about a dozen requests and university
    projects file under the university anyway. Enable it per run with `patents=True` (CLI: --patents).
    """
    from context.cache import Cache
    cache = cache if cache is not None else Cache()
    found = {"cache": cache, "model": model}
    for name, module, func in (("imprint", "context.imprint", "imprint_lookup"), ("grants", "context.foekat", "grant_lookup"),
                               ("web_history", "context.wayback", "web_history_lookup"), ("classify", "context.classify", "classify_texts"),
                               ("author", "context.openalex", "author_lookup"), ("idw", "context.idw", "idw_lookup"),
                               ("patents", "context.patents", "patent_lookup")):
        if name == "patents" and not patents:
            found[name] = None
            continue
        try:
            found[name] = getattr(__import__(module, fromlist=[func]), func)
        except (ImportError, AttributeError) as exc:
            found[name] = None
            logger.warning("Lookup %s nicht verfügbar: %s", name, exc)
    return found


def cached_quotes(extract_quotes: Callable, cache) -> Callable:
    """Memoise Tom's Ollama quote extractor in the shared cache so a second run yields the same quotes."""
    import hashlib
    import json as _json

    def wrapped(name, signals, fields):
        key = "quotes:" + hashlib.sha1(_json.dumps([name, sorted(fields), [(str(s.url), s.evidence) for s in signals]],
                                                   ensure_ascii=False).encode("utf-8")).hexdigest()
        hit = cache.get(key) if cache is not None else None
        if hit is None:
            hit = [(field, quote, str(signal.url)) for field, quote, signal in extract_quotes(name, signals, fields)]
            if cache is not None:
                cache.set(key, hit)
        by_url = {str(s.url): s for s in signals}
        return [(field, quote, by_url[url]) for field, quote, url in hit if url in by_url]
    return wrapped


def _run(lookups: dict, name: str, merged: Lookup, call):
    """Run one lookup; a failing lookup becomes an error entry instead of aborting the lead."""
    func = lookups.get(name)
    if func is None:
        if name != "patents":
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


def enrich(
    lead: RawLead, *, load_pages: Callable[[str], Iterable[SourceSignal]] = company_pages,
    load_original: Callable[[str], SourceSignal | None] | None = None,
    extract_quotes: Callable | None = None,
    light: bool = False, lookups: dict | None = None,
    as_of: date | None = None,
) -> EnrichedLead:
    """Return the original lead plus public context and per-field evidence."""
    signals = list(lead.signals)
    if light:
        lookups = None  # light mode never calls external services
    page_cache = lookups.get("cache") if lookups else None
    if page_cache is not None and load_pages is company_pages:
        load_pages = partial(company_pages, cache=page_cache)
    if page_cache is not None and load_original is not None and getattr(load_original, "__name__", "") == "original_page":
        load_original = partial(load_original, cache=page_cache)
    if lead.website and not lead.is_demo and not light:
        signals.extend(load_pages(str(lead.website)))
    if (load_original and not lead.is_demo and not light
            and not any(signal.url == lead.source_url for signal in signals)):
        if original := load_original(str(lead.source_url)):
            signals.append(original)
    merged = Lookup()
    grants, patents, profiles_by_name = [], [], {}
    # Earliest dated sourcing signal (e.g. the EXIST project start): bounds namesake hits from the lookups.
    earliest = min((s.date for s in lead.signals if s.date is not None), default=None)
    # Step 1 delivers the catalogue row as labelled text: the grant is documented without any lookup (also --light).
    offline = [hit for s in lead.signals if not lead.is_demo and (hit := catalogue_grant(s))]
    offline_grants = [grant for grant, _, _ in offline]
    grant_institution = next((f["recipient"].split(",")[0].strip() for _, _, f in offline if f["recipient"]), None) or None
    exclude_names = [text for _, _, f in offline for text in (f["recipient"], f["executing"]) if text]
    namesake_urls = set()
    if lookups and not lead.is_demo:
        cache = lookups.get("cache")
        if lead.website:
            _run(lookups, "imprint", merged, lambda f: f(str(lead.website), cache=cache))
        reference = next((f["fkz"] for _, _, f in offline), None) or next(
            (m.group(0) for s in signals for m in [re.search(r"(?<![A-Za-z0-9])03E[FG][A-Za-z0-9]{3,}", s.evidence)] if m), None)
        institution = merged.fields.get("institution")
        result = _run(lookups, "grants", merged, lambda f: f(lead.name, institution=grant_institution or institution or lead.location,
                                                             reference=reference, cache=cache))
        if result:
            grants = list(result[0])
        institution = grant_institution or institution or next(
            (re.split(r",| - ", g.recipient)[0].strip() for g in grants if g.recipient), None)
        history_kwargs = {"not_before": earliest} if earliest and _accepts(lookups.get("web_history"), "not_before") else {}
        _run(lookups, "web_history", merged, lambda f: f(str(lead.website) if lead.website else None, lead.name, cache=cache,
                                                         **history_kwargs))
        _run(lookups, "idw", merged, lambda f: f(lead.name, institution=institution, founders=list(lead.founders), cache=cache))
        result = _run(lookups, "patents", merged, lambda f: f(lead.name, list(lead.founders), cache=cache))
        patents = list(result[0]) if result else []
        # A press article from years before the first sourced signal is about a namesake ("procado Consulting",
        # 2013, for a 2025 EXIST project): it must neither date the lead earlier nor feed the classifier.
        cutoff = _years_before(earliest, 2) if earliest else None
        for s in merged.signals:
            if cutoff and s.type == "idw" and s.date is not None and s.date < cutoff:
                namesake_urls.add(str(s.url))
                merged.errors.append("idw: Artikel %s vom %s vor erstem Signal, vermutlich Namensvetter" % (s.url, s.date.isoformat()))
        signals.extend(s for s in merged.signals if str(s.url) not in namesake_urls)
        terms = field_terms(lead)
        for founder in dict.fromkeys(lead.founders):
            result = _run(lookups, "author", merged, lambda f, n=founder: f(n, institution=institution, field_terms=terms, cache=cache))
            if result and result[0] is not None:
                profiles_by_name[founder] = result[0]
    known = {g.reference for g in grants if g.reference}
    grants = grants + [g for g in offline_grants if not g.reference or g.reference not in known]   # looked-up grant wins
    evidence = [e for e in merged.evidence if str(e.url) not in namesake_urls] + [e for _, e, _ in offline]
    # Frozen source excerpts for the replayable scoring handoff, incl. lookup texts (Impressum, idw, Förderkatalog).
    scoring_sources = [signal.model_copy(deep=True) for signal in signals] if not lead.is_demo else None
    evidence_by_key = {}
    facts = defaultdict(dict)
    discovery = []

    def record(field, value, excerpt, signal, *, model_quote=False, sourcing=False):
        key = (field, signal.url, signal.date, excerpt)
        if key not in evidence_by_key:
            item = Evidence(field=field, source=signal.source, url=signal.url,
                            source_date=signal.date, finding=excerpt,
                            verification_status=("assumption" if lead.is_demo else
                                                 "unverified" if sourcing else "source_matched"))
            evidence_by_key[key] = item
            evidence.append(item)
        item = evidence_by_key[key]
        claim = facts[field].setdefault(value.casefold(), Claim(
            value=value, evidence_ids=[item.evidence_id],
            origin="model_selected_quote" if model_quote else "source_statement",
        ))
        if item.evidence_id not in claim.evidence_ids:
            claim.evidence_ids.append(item.evidence_id)
        return item

    def claim_for(field):
        values = facts[field]
        return next(iter(values.values())) if len(values) == 1 else None

    def unambiguous(field):
        claim = claim_for(field)
        return claim.value if claim else None

    source = SourceSignal(source=lead.source_name or "Sourcing", url=lead.source_url,
                          type="sourcing", evidence=lead.description.strip() or lead.name)
    if lead.has_vc is not None:
        record("vc_status", "confirmed" if lead.has_vc else "reported_none",
               f"has_vc = {str(lead.has_vc).lower()}", source, sourcing=True)
    if lead.location:
        record("company.reported_location", lead.location, f"Standort laut Sourcing: {lead.location}",
               source, sourcing=True)

    founders = list(dict.fromkeys(lead.founders))
    for signal in signals:
        if signal in lead.signals:
            item = record("discovery_signals", signal.evidence[:1000], signal.evidence[:1000], signal)
            if item not in discovery:
                discovery.append(item)
        if signal.date is not None and not mention_only(signal):
            record("first_signal_date", signal.date.isoformat(), signal.evidence[:1000], signal)
        for line in statements(signal):
            if len(line) > 1000:
                continue
            for field, labels in LABELS.items():
                if value := labelled(line, labels):
                    record(field, value, line, signal)
                elif field in PROSE and (match := re.fullmatch(PROSE[field], line, re.IGNORECASE)):
                    record(field, match[1], line, signal)
            for field, labels in RESEARCH_LABELS.items():
                if value := labelled(line, labels):
                    if field == "company.founding_date":
                        try:
                            if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", value):
                                value = datetime.strptime(value, "%d.%m.%Y").date().isoformat()
                            else:
                                value = date.fromisoformat(value.strip(".")).isoformat()
                        except ValueError:
                            continue
                    record(field, value, line, signal)
            for field, labels in MONEY_LABELS.items():
                if (value := labelled(line, labels)) and (amount := euros(value)):
                    record(field, str(amount), line, signal)
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
                    record(f"traction.metrics.{metric}.{match[1]}", format(Decimal(number).normalize(), "f"), line, signal)
            product = labelled(line, "Produktreife|Produktstatus|Product stage")
            if product and (stage := stage_value(product, PRODUCT_STAGES)):
                record("product_stage", stage, line, signal)
            elif stage_value(line, {"mvp": r"(?:Unser MVP ist (?:fertig|verfügbar)|Our MVP is (?:ready|available))"}):
                record("product_stage", "mvp", line, signal)
            funding = labelled(line, "Finanzierungsstatus|Funding status")
            if funding and (status := stage_value(funding, FUNDING)):
                record("funding_status", status, line, signal)
                if status == "vc_backed":
                    record("vc_status", "confirmed", line, signal)
            elif round_match := re.fullmatch(
                r"Wir haben (?:unsere|eine) (Pre-Seed|Seed|Series [A-Z])[- ]Runde abgeschlossen[.!]?"
                r"|We (?:have )?closed (?:our|a) (Pre-Seed|Seed|Series [A-Z]) round[.!]?",
                line, re.IGNORECASE,
            ):
                record("funding_status", "funded", line, signal)
                record("funding_stage", round_match[1] or round_match[2], line, signal)
                record("funding.rounds", round_match[1] or round_match[2], line, signal)
            vc = labelled(line, "VC-Status|VC status")
            if vc and stage_value(vc, {"confirmed": r"Ja|Yes|Vorhanden|VC-backed"}):
                record("vc_status", "confirmed", line, signal)
            if vc and stage_value(vc, {"none": r"Nein|No|Kein VC|No VC"}):
                record("vc_status", "reported_none", line, signal)
            for index, name in enumerate(founders):
                person = re.escape(" ".join(name.split()))
                for field, label in FOUNDER_FIELDS.items():
                    if value := labelled(line, rf"{person}\s+[\-–]\s+(?:{label})"):
                        record(f"founder_profiles.{index}.{field}", value, line, signal)
                role = re.fullmatch(
                    rf"{person}\s*(?:\||[–—-]|,\s)\s*"
                    r"(CEO|CTO|COO|CFO|CPO|Co-Founder|Co-Gründer(?:in)?|Geschäftsführer(?:in)?)",
                    line, re.IGNORECASE,
                )
                if role:
                    record(f"founder_profiles.{index}.role", role[1], line, signal)
                background = re.fullmatch(
                    rf"{person}\s+(?:promovierte in|studierte|has a PhD in|studied)\s+.+",
                    line, re.IGNORECASE,
                )
                if background:
                    record(f"founder_profiles.{index}.qualifications", line, line, signal)

    if lookups and not lead.is_demo and lookups.get("classify"):
        before = len(merged.evidence)
        # Sourcing's own one-line summaries are not company statements; only real excerpts are classified.
        summaries = {id(s) for s in lead.signals if len(s.evidence) < 200}
        texts = [s for s in signals if id(s) not in summaries]
        classify_kwargs = {"exclude_names": exclude_names} if exclude_names and _accepts(lookups.get("classify"), "exclude_names") else {}
        _run(lookups, "classify", merged, lambda f: f(lead.name, texts, model=lookups.get("model"), cache=lookups.get("cache"),
                                                       founders=list(lead.founders), **classify_kwargs))
        evidence.extend(merged.evidence[before:])
        for name in ("product_stage",):  # rules in this file win over the classifier
            if facts[name] and name in merged.fields:
                del merged.fields[name]
    model_failed = False
    if extract_quotes and lookups and lookups.get("cache") is not None:
        extract_quotes = cached_quotes(extract_quotes, lookups["cache"])
    if extract_quotes and not light:
        text_fields = [*LABELS, *(f"product.{field}" for field in PRODUCT_FIELDS)]
        missing = tuple(field for field in text_fields if field != "funding_stage" and not facts[field])
        # Only the company's own statements and press texts are quotable; catalogue rows, archive stubs and
        # sourcing summaries would turn a grant sum into "capital need".
        quotable = [s for s in signals if s.type not in {"exist_projekt", "foerderprojekt", "wayback", "sourcing", "demo"}
                    and "for sale" not in s.evidence.lower()]
        if missing and quotable:
            try:
                model_signals = [signal.model_copy(deep=True) for signal in quotable]
                for field, quote, signal in extract_quotes(lead.name, model_signals, missing):
                    if field in missing and signal in quotable and quote.strip() and quote in signal.evidence:
                        record(field, quote, quote, SourceSignal(source="Ollama-Zitat aus " + signal.source, type=signal.type,
                                                                 url=signal.url, date=signal.date, evidence=signal.evidence),
                               model_quote=True)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                model_failed = True
                merged.errors.append("ollama: %s" % type(exc).__name__)

    vc_status = unambiguous("vc_status") or ("conflicting" if facts["vc_status"] else "unknown")
    funding_facts = set(facts["funding_status"])
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
    questions = [question for field, question in QUESTIONS.items() if unambiguous(field) is None]
    if vc_status in {"conflicting", "unknown"}:
        questions.append("Welche Investoren sind bereits beteiligt?")
    if unambiguous("product_stage") is None and not merged.fields.get("product_stage"):
        questions.append("Welcher Produktstand ist heute nachweisbar?")
    if not founders or any(
        unambiguous(f"founder_profiles.{i}.{field}") is None
        for i in range(len(founders)) for field in ("role", "qualifications")
    ):
        questions.append("Wer gehört zum Gründungsteam und wer bringt welche Erfahrung mit?")
    if model_failed:
        questions.append("Welche offenen Angaben lassen sich anhand der Originalquellen bestätigen?")
    if not claim_for("customer_problem"):
        questions.append("Welches konkrete Kundenproblem löst ihr?")
    if not claim_for("target_customers"):
        questions.append("Welche Kundengruppe nutzt das Produkt?")

    founding_claim = claim_for("company.founding_date")
    founding_status = "documented" if founding_claim else "unknown"
    if lead.founding_year:
        raw_date = f"{lead.founding_year:04}"
        if lead.founding_month:
            raw_date += f"-{lead.founding_month:02}"
        record("company.reported_founding_date", raw_date, f"Gründung laut Sourcing: {raw_date}",
               source, sourcing=True)
        if founding_claim is None:
            founding_claim = claim_for("company.reported_founding_date")
            founding_status = "reported"
        elif not founding_claim.value.startswith(raw_date):
            founding_status = "conflicting"
    if len(facts["company.founding_date"]) > 1:
        founding_status = "conflicting"
    if founding_status == "conflicting":
        founding_claim = None
        questions.append("Wann und in welcher Rechtsform wurde das Unternehmen gegründet?")

    round_terms = {field: int(value) if (value := unambiguous(field)) else None for field in MONEY_LABELS}
    reported_metrics = defaultdict(list)
    for field in sorted(key for key in facts if key.startswith("traction.metrics.")):
        if claim := claim_for(field):
            _, _, metric, year = field.split(".")
            _, unit, currency = PERIOD_METRICS[metric]
            reported_metrics[metric].append(MarketMeasure(
                value=float(claim.value), unit=unit, currency=currency, geography="Unternehmensebene",
                period=Period(start_year=int(year), end_year=int(year)),
                methodology="Explizit veröffentlichte Jahresangabe des Unternehmens oder der Fundquelle",
                data_type="assumption" if lead.is_demo else "observed", evidence_ids=claim.evidence_ids,
            ))

    def latest_metric(metric):
        prefix = f"traction.metrics.{metric}."
        latest = max((key for key in facts if key.startswith(prefix)), default=None)
        return unambiguous(latest) if latest else None

    revenue = latest_metric("revenue")
    customers = latest_metric("customer_count")
    context = ContextV2(
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
            **{field: list(facts[f"traction.{field}"].values()) for field in TRACTION_EVENTS},
            **{field: claim_for(f"traction.{field}") for field in TRACTION_METRICS},
            reported_metrics=dict(reported_metrics),
        ),
        funding=FundingResearch(
            status=funding_status, vc_status=vc_status, capital_need=claim_for("capital_need"),
            status_evidence_ids=list(dict.fromkeys(
                evidence_id for field in ("funding_status", "vc_status")
                for claim in facts[field].values() for evidence_id in claim.evidence_ids
            )),
            **{field: list(facts[f"funding.{field}"].values()) for field in FUNDING_EVENTS},
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
    extra = {k: v for k, v in merged.fields.items() if k in EnrichedLead.model_fields and k not in RawLead.model_fields
             and k not in {"evidence", "founder_profiles", "research_questions", "product_stage", "funding_status", "vc_status",
                           "first_signal_date", "enrichment_sources", "enrichment_errors", "grants", "patents"}}
    if grants:
        extra["grants"] = grants
    if merged.fields.get("contact_email") and not lead.contact_email:
        extra["imprint_email"] = merged.fields["contact_email"]
    def plausible(year):
        """A project that started under EXIST in 2025 was not founded in 2013: reject hints > 2 years before it."""
        if earliest and year < earliest.year - 2:
            message = "idw: Gründungsjahr %d verworfen (vor erstem Signal)" % year
            if message not in merged.errors:
                merged.errors.append(message)
            return False
        return True

    extra.pop("founding_year_hint", None)      # set below only after the plausibility checks
    hint = merged.fields.get("founding_year_hint")
    if isinstance(hint, int) and not plausible(hint):
        hint = None
    if not isinstance(hint, int):  # "X wurde gegründet" without a year: the article date bounds the founding year
        lead_re = name_pattern(lead.name)       # umlaut-folded, legal form stripped, whole word
        articles = {str(s.url): s for s in merged.signals if s.type == "idw"}

        def about_lead(url):
            article = articles.get(str(url))
            if article is None or lead_re is None:
                return False
            title = article.evidence.split("\n", 1)[0]
            return bool(lead_re.search(idw_fold(title))) or len(lead_re.findall(idw_fold(article.evidence))) >= 2

        for e in merged.evidence:
            if (e.field == "founding_statement" and e.source_date and lead_re is not None and lead_re.search(idw_fold(e.finding))
                    and re.search(r"(?i)\bgegründet\b|\bGründung (von|der) |was founded|founded in|has been founded", e.finding)
                    and not re.search(r"(?i)geplant|planen|plant |gegründet werden|soll|wird gegründet|bereitet .* vor|vorbereitet|in Gründung|zu gründen", e.finding)
                    and about_lead(e.url) and plausible(e.source_date.year)):
                hint = e.source_date.year
                evidence.append(Evidence(field="founding_year_mention", url=e.url, finding=e.finding, source=e.source, source_date=e.source_date))
                break
    if isinstance(hint, int) and 1900 <= hint <= 2100:
        extra["founding_year_hint"] = hint
    patents = patents + [x for x in merged.fields.get("patents", []) if x not in patents]
    if patents:
        extra["patents"] = patents
    if lookups and not lead.is_demo:
        questions = [q for q in questions if not (q.startswith("Welchen Kapitalbedarf") and extra.get("grants"))]
        if "legal_form" not in extra:
            questions.append("Welche Rechtsform hat das Vorhaben heute (Impressum nicht gefunden)?")
        if "ip_status" not in extra:
            questions.append("Gibt es Schutzrechte oder Patentanmeldungen?")
        if not extra.get("partners"):
            questions.append("Welche Piloten, Design-Partner oder Absichtserklärungen gibt es?")
    founder_profiles = []
    for index, name in enumerate(founders):
        base = profiles_by_name.get(name)
        values = base.model_dump() if base else {"name": name}
        values["role"] = unambiguous(f"founder_profiles.{index}.role")
        values["qualifications"] = unambiguous(f"founder_profiles.{index}.qualifications") or values.get("qualifications")
        founder_profiles.append(FounderProfile(**values))
    sources = merged.fields.pop("_sources", [])
    values = dict(
        evidence=evidence,
        context_v2=context,
        scoring_sources=scoring_sources,
        founder_profiles=founder_profiles,
        **{field: unambiguous(field) for field in LABELS},
        **round_terms,
        research_questions=questions,
        product_stage=unambiguous("product_stage") or merged.fields.get("product_stage"),
        funding_status=funding_status,
        vc_status=vc_status,
        first_signal_date=min((signal.date for signal in signals if signal.date is not None and not mention_only(signal)),
                              default=None),
        founded_on=date.fromisoformat(founding_claim.value) if founding_status == "documented" else None,
        annual_revenue_eur=float(revenue) if revenue is not None else None,
        customer_count=int(customers) if customers is not None else None,
        enrichment_sources=sources,
        enrichment_errors=merged.errors,
    )
    values.update({k: v for k, v in extra.items() if k not in values})
    enriched = EnrichedLead(**lead.model_dump(), **values)
    if not lead.is_demo:
        enriched.scoring_input = build_scoring_input(enriched, as_of=as_of)
    return enriched
