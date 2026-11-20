"""Extract evidenced facts from sourcing signals and public company pages."""
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal

from context.web import company_pages
from models import EnrichedLead, Evidence, FounderProfile, RawLead, SourceSignal

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


def labelled(line, labels):
    match = re.fullmatch(rf"(?:{labels})\s*[:–]\s*(.+)", line, re.IGNORECASE)
    return match[1].strip() if match else None


def statements(signal):
    """Treat a text block as a heading/value pair only for recognized labels."""
    lines = [" ".join(line.split()) for line in signal.evidence.splitlines() if line.strip()]
    headings = "|".join([*LABELS.values(), *MONEY_LABELS.values(), "Produktreife|Produktstatus|Product stage",
                         "Finanzierungsstatus|Funding status|VC-Status|VC status"])
    for i, line in enumerate(lines):
        yield line
        if i + 1 < len(lines) and re.fullmatch(headings, line, re.IGNORECASE):
            yield f"{line}: {lines[i + 1]}"


def enrich(
    lead: RawLead, *, load_pages: Callable[[str], Iterable[SourceSignal]] = company_pages,
    load_original: Callable[[str], SourceSignal | None] | None = None,
    extract_quotes: Callable | None = None,
) -> EnrichedLead:
    """Return the original lead plus public context and per-field evidence."""
    signals = list(lead.signals)
    if lead.website and not lead.is_demo:
        signals.extend(load_pages(str(lead.website)))
    if (load_original and not lead.is_demo
            and not any(signal.url == lead.source_url for signal in signals)):
        if original := load_original(str(lead.source_url)):
            signals.append(original)
    evidence = []
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

    model_failed = False
    if extract_quotes:
        missing = tuple(field for field in LABELS if field != "funding_stage" and not facts[field])
        if missing:
            try:
                for field, quote, signal in extract_quotes(lead.name, signals, missing):
                    if field in missing and signal in signals and quote.strip() and quote in signal.evidence:
                        record(field, quote, quote, signal)
            except (OSError, ValueError, KeyError, TypeError):
                model_failed = True

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
    questions = [question for field, question in QUESTIONS.items() if unambiguous(field) is None]
    if vc_status in {"conflicting", "unknown"}:
        questions.append("Welche Investoren sind bereits beteiligt?")
    if unambiguous("product_stage") is None:
        questions.append("Welcher Produktstand ist heute nachweisbar?")
    if not founders or any(
        unambiguous(f"founder_profiles.{i}.{field}") is None
        for i in range(len(founders)) for field in ("role", "qualifications")
    ):
        questions.append("Wer gehört zum Gründungsteam und wer bringt welche Erfahrung mit?")
    if model_failed:
        questions.append("Welche offenen Angaben lassen sich anhand der Originalquellen bestätigen?")
    return EnrichedLead(
        **lead.model_dump(),
        evidence=evidence,
        founder_profiles=[
            FounderProfile(name=name, role=unambiguous(f"founder_profiles.{index}.role"),
                           qualifications=unambiguous(f"founder_profiles.{index}.qualifications"))
            for index, name in enumerate(founders)
        ],
        **{field: unambiguous(field) for field in LABELS},
        **{field: int(value) if (value := unambiguous(field)) else None for field in MONEY_LABELS},
        research_questions=questions,
        product_stage=unambiguous("product_stage"),
        funding_status=funding_status,
        vc_status=vc_status,
        first_signal_date=min((signal.date for signal in signals if signal.date is not None), default=None),
    )
