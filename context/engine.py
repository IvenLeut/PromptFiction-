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
from decimal import Decimal
from functools import partial

from context.lookup import Lookup
from context.web import company_pages
from models import EnrichedLead, Evidence, FounderProfile, RawLead, SourceSignal

logger = logging.getLogger(__name__)
STOPWORDS = set("""für mit und oder der die das des dem den ein eine einer eines einem einen von zur zum auf aus bei nach über unter durch
ohne gegen sowie auch nicht sind wird werden wurde kann können soll sollen haben hat ist sein ihre ihrer seine seiner unsere unser
entwickelt entwickeln bietet bieten ermöglicht basierend neue neuen neuer innovative innovativ lösung lösungen plattform software system
systeme technologie unternehmen startup start-up produkt produkte kunden projekt the and for with from that this into using based
develops developing provides solution solutions platform company customers product products technology""".split())

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
    "am_markt": r"Am Markt|Marktreif und verfügbar|Commercially available|On the market|Launched",
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
        if re.fullmatch(r"[1-9]\d{0,2}(?:[., ]\d{3}){1,4}|[1-9]\d{0,14}", amount):
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
    headings = "|".join([*LABELS.values(), *MONEY_LABELS.values(), "Produktreife|Produktstatus|Product stage",
                         "Finanzierungsstatus|Funding status|VC-Status|VC status"])
    for i, line in enumerate(lines):
        yield line
        if i + 1 < len(lines) and re.fullmatch(headings, line, re.IGNORECASE):
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
    extract_quotes: Callable | None = None, lookups: dict | None = None,
) -> EnrichedLead:
    """Return the original lead plus public context and per-field evidence."""
    signals = list(lead.signals)
    page_cache = lookups.get("cache") if lookups else None
    if page_cache is not None and load_pages is company_pages:
        load_pages = partial(company_pages, cache=page_cache)
    if page_cache is not None and load_original is not None and getattr(load_original, "__name__", "") == "original_page":
        load_original = partial(load_original, cache=page_cache)
    if lead.website and not lead.is_demo:
        signals.extend(load_pages(str(lead.website)))
    if (load_original and not lead.is_demo
            and not any(signal.url == lead.source_url for signal in signals)):
        if original := load_original(str(lead.source_url)):
            signals.append(original)
    merged = Lookup()
    grants, patents, profiles_by_name = [], [], {}
    if lookups and not lead.is_demo:
        cache = lookups.get("cache")
        if lead.website:
            _run(lookups, "imprint", merged, lambda f: f(str(lead.website), cache=cache))
        reference = next((m.group(0) for s in signals for m in [re.search(r"(?<![A-Za-z0-9])03E[FG][A-Za-z0-9]{3,}", s.evidence)] if m), None)
        institution = merged.fields.get("institution")
        result = _run(lookups, "grants", merged, lambda f: f(lead.name, institution=institution or lead.location, reference=reference, cache=cache))
        if result:
            grants = list(result[0])
            institution = institution or next((re.split(r",| - ", g.recipient)[0].strip() for g in grants if g.recipient), None)
        _run(lookups, "web_history", merged, lambda f: f(str(lead.website) if lead.website else None, lead.name, cache=cache))
        _run(lookups, "idw", merged, lambda f: f(lead.name, institution=institution, founders=list(lead.founders), cache=cache))
        result = _run(lookups, "patents", merged, lambda f: f(lead.name, list(lead.founders), cache=cache))
        patents = list(result[0]) if result else []
        signals.extend(merged.signals)
        terms = field_terms(lead)
        for founder in dict.fromkeys(lead.founders):
            result = _run(lookups, "author", merged, lambda f, n=founder: f(n, institution=institution, field_terms=terms, cache=cache))
            if result and result[0] is not None:
                profiles_by_name[founder] = result[0]
    evidence = list(merged.evidence)
    seen_evidence = set()
    facts = defaultdict(dict)

    def record(field, value, excerpt, signal):
        facts[field].setdefault(value.casefold(), value)
        key = (field, signal.url, signal.date, excerpt)
        if key not in seen_evidence:
            seen_evidence.add(key)
            evidence.append(Evidence(field=field, source=signal.source, url=signal.url,
                                     source_date=signal.date, finding=excerpt))

    def unambiguous(field):
        values = facts[field]
        return next(iter(values.values())) if len(values) == 1 else None

    if lead.has_vc is not None:
        source = SourceSignal(source=lead.source_name or "Sourcing", url=lead.source_url,
                              type="sourcing", evidence=f"has_vc = {str(lead.has_vc).lower()}")
        record("vc_status", "confirmed" if lead.has_vc else "reported_none", source.evidence, source)

    founders = list(dict.fromkeys(lead.founders))
    for signal in signals:
        if signal.date is not None:
            record("first_signal_date", signal.date.isoformat(), signal.evidence[:1000], signal)
        for line in statements(signal):
            if len(line) > 1000:
                continue
            for field, labels in LABELS.items():
                if value := labelled(line, labels):
                    record(field, value, line, signal)
                elif field in PROSE and (match := re.fullmatch(PROSE[field], line, re.IGNORECASE)):
                    record(field, match[1], line, signal)
            for field, labels in MONEY_LABELS.items():
                if (value := labelled(line, labels)) and (amount := euros(value)):
                    record(field, str(amount), line, signal)
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
            vc = labelled(line, "VC-Status|VC status")
            if vc and stage_value(vc, {"confirmed": r"Ja|Yes|Vorhanden|VC-backed"}):
                record("vc_status", "confirmed", line, signal)
            if vc and stage_value(vc, {"none": r"Nein|No|Kein VC|No VC"}):
                record("vc_status", "reported_none", line, signal)
            for index, name in enumerate(founders):
                person = re.escape(" ".join(name.split()))
                for field, label in (("role", "Rolle|Role"), ("qualifications", "Qualifikation|Hintergrund|Background|Experience")):
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
        _run(lookups, "classify", merged, lambda f: f(lead.name, texts, model=lookups.get("model"), cache=lookups.get("cache"),
                                                       founders=list(lead.founders)))
        evidence.extend(merged.evidence[before:])
        for name in ("product_stage",):  # rules in this file win over the classifier
            if facts[name] and name in merged.fields:
                del merged.fields[name]
    model_failed = False
    if extract_quotes and lookups and lookups.get("cache") is not None:
        extract_quotes = cached_quotes(extract_quotes, lookups["cache"])
    if extract_quotes:
        missing = tuple(field for field in LABELS if field != "funding_stage" and not facts[field])
        # Only the company's own statements and press texts are quotable; catalogue rows, archive stubs and
        # sourcing summaries would turn a grant sum into "capital need".
        quotable = [s for s in signals if s.type not in {"exist_projekt", "foerderprojekt", "wayback", "sourcing", "demo"}
                    and "for sale" not in s.evidence.lower()]
        if missing and quotable:
            try:
                for field, quote, signal in extract_quotes(lead.name, quotable, missing):
                    if field in missing and signal in quotable and quote.strip() and quote in signal.evidence:
                        record(field, quote, quote, SourceSignal(source="Ollama-Zitat aus " + signal.source, type=signal.type,
                                                                 url=signal.url, date=signal.date, evidence=signal.evidence))
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
    extra = {k: v for k, v in merged.fields.items() if k in EnrichedLead.model_fields and k not in RawLead.model_fields
             and k not in {"evidence", "founder_profiles", "research_questions", "product_stage", "funding_status", "vc_status",
                           "first_signal_date", "enrichment_sources", "enrichment_errors", "grants", "patents"}}
    if grants:
        extra["grants"] = grants
    if merged.fields.get("contact_email") and not lead.contact_email:
        extra["imprint_email"] = merged.fields["contact_email"]
    hint = merged.fields.get("founding_year_hint")
    if not isinstance(hint, int):  # "X wurde gegründet" without a year: the article date bounds the founding year
        folded = lead.name.lower()
        for e in merged.evidence:
            if (e.field == "founding_statement" and e.source_date and folded.split()[0] in e.finding.lower()
                    and re.search(r"(?i)\bgegründet\b|\bGründung (von|der) |was founded|founded in|has been founded", e.finding)
                    and not re.search(r"(?i)geplant|planen|plant |gegründet werden|soll|wird gegründet|bereitet .* vor|vorbereitet|in Gründung|zu gründen", e.finding)):
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
    return EnrichedLead(
        **lead.model_dump(),
        evidence=evidence,
        founder_profiles=founder_profiles,
        **{field: unambiguous(field) for field in LABELS},
        **{field: int(value) if (value := unambiguous(field)) else None for field in MONEY_LABELS},
        research_questions=questions,
        product_stage=unambiguous("product_stage") or merged.fields.get("product_stage"),
        funding_status=funding_status,
        vc_status=vc_status,
        first_signal_date=min((signal.date for signal in signals if signal.date is not None), default=None),
        enrichment_sources=sources,
        enrichment_errors=merged.errors,
        **extra,
    )
