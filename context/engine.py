"""Extract evidenced facts from sourcing signals and public company pages."""
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime
from decimal import Decimal

from context.company import (
    COMPANY_FIELDS, FOUNDER_FIELDS, FUNDING_EVENTS, FUNDING_FIELDS, PRODUCT_FIELDS,
    RESEARCH_LABELS, TRACTION_EVENTS, TRACTION_METRICS,
)
from context.web import company_pages
from models import EnrichedLead, Evidence, FounderProfile, RawLead, SourceSignal
from research_models import (
    Claim, CompanyResearch, ContextV2, FounderResearch, FundingResearch, MarketMeasure, Period,
    ProductResearch, ResearchStatus, TractionResearch,
)

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


def labelled(line, labels):
    match = re.fullmatch(rf"(?:{labels})\s*[:–]\s*(.+)", line, re.IGNORECASE)
    return match[1].strip() if match else None


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


def enrich(
    lead: RawLead, *, load_pages: Callable[[str], Iterable[SourceSignal]] = company_pages,
    load_original: Callable[[str], SourceSignal | None] | None = None,
    extract_quotes: Callable | None = None,
    light: bool = False,
) -> EnrichedLead:
    """Return the original lead plus public context and per-field evidence."""
    signals = list(lead.signals)
    if lead.website and not lead.is_demo and not light:
        signals.extend(load_pages(str(lead.website)))
    if (load_original and not lead.is_demo and not light
            and not any(signal.url == lead.source_url for signal in signals)):
        if original := load_original(str(lead.source_url)):
            signals.append(original)
    evidence = []
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

    model_failed = False
    if extract_quotes and not light:
        text_fields = [*LABELS, *(f"product.{field}" for field in PRODUCT_FIELDS)]
        missing = tuple(field for field in text_fields if field != "funding_stage" and not facts[field])
        if missing:
            try:
                for field, quote, signal in extract_quotes(lead.name, signals, missing):
                    if field in missing and signal in signals and quote.strip() and quote in signal.evidence:
                        record(field, quote, quote, signal, model_quote=True)
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
    return EnrichedLead(
        **lead.model_dump(),
        evidence=evidence,
        context_v2=context,
        founder_profiles=[
            FounderProfile(name=name, role=unambiguous(f"founder_profiles.{index}.role"),
                           qualifications=unambiguous(f"founder_profiles.{index}.qualifications"))
            for index, name in enumerate(founders)
        ],
        **{field: unambiguous(field) for field in LABELS},
        **round_terms,
        research_questions=questions,
        product_stage=unambiguous("product_stage"),
        funding_status=funding_status,
        vc_status=vc_status,
        first_signal_date=min((signal.date for signal in signals if signal.date is not None), default=None),
        founded_on=date.fromisoformat(founding_claim.value) if founding_status == "documented" else None,
        annual_revenue_eur=float(revenue) if revenue is not None else None,
        customer_count=int(customers) if customers is not None else None,
    )
