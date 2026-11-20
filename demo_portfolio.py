"""Deterministic, fully fictional step-3 output for dashboard development."""
from datetime import datetime, timezone

from models import EvaluatedLead, EnrichedLead, RawLead, Evidence, Industry, ResearchResult

PROFILES = [
    (Industry.AI, "Dokumentenprüfung für industrielle Lieferketten", "kürzere Prüfzeiten", "Zugang zu kundeneigenen Trainingsdaten"),
    (Industry.CLIMATE, "Wärmespeicher für mittelständische Betriebe", "effizientere Nutzung erneuerbarer Wärme", "Kapitalbedarf für Hardware-Piloten"),
    (Industry.HEALTH, "Software zur Koordination klinischer Studien", "weniger administrative Arbeit", "lange Beschaffungs- und Freigabezyklen"),
    (Industry.FINTECH, "Liquiditätsplanung für kleine Unternehmen", "frühere Erkennung von Liquiditätsengpässen", "Abhängigkeit von Banking-Schnittstellen"),
    (Industry.INDUSTRIAL, "Sensorik für vorausschauende Wartung", "geringere ungeplante Stillstandszeiten", "aufwendige Integration in Bestandsanlagen"),
]
PREFIXES = ["Aven", "Briva", "Caleo", "Dovra", "Eluno", "Faryn"]
SUFFIXES = ["Logic", "Therm", "Care", "Flow", "Sense"]


def get_demo_result(industry_filter: Industry | None = None) -> ResearchResult:
    leads = []
    for i in range(30):
        profile_index = list(Industry).index(industry_filter) if industry_filter else i % 5
        industry, product, benefit, risk = PROFILES[profile_index]
        name = f"{PREFIXES[i // 5]}{SUFFIXES[profile_index]} {['Labs', 'Systems', 'Works', 'One', 'Nova'][i % 5]}"
        slug = f"{industry.name.lower()}-{i + 1:02}"
        url = f"https://example.org/{slug}"
        source = ["Unternehmensregister", "GitHub", "Hochschul-Inkubator"][i % 3]
        company = 48 + (i * 13 % 49)
        market = 45 + (i * 17 % 53)
        risk_score = 15 + (i * 19 % 71)
        # Fixture-only formula: not an approved investment methodology.
        overall = round(.45 * company + .35 * market + .20 * (100 - risk_score), 1)
        evidence = Evidence(source=f"{source} – fiktiver Beleg", url=f"{url}/source",
                            finding="Simulierter Fund und deutscher Standort; kein realer Registereintrag.",
                            field="country", retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc))
        leads.append(EvaluatedLead(
            id=slug, name=name, description=f"Entwickelt {product}.",
            industry=industry, country="DE", location=["Berlin", "München", "Hamburg", "Köln", "Dresden"][i % 5],
            source_url=evidence.url, source_name=source, country_evidence=evidence, is_demo=True,
            website=None if i % 11 == 0 else url,
            founders=[f"Demo-Gründerin {i + 1:02}", f"Demo-Mitgründer {i + 1:02}"],
            contact_email=None if i % 7 == 0 else f"founder.{i + 1:02}@example.org",
            founding_year=2024 + i % 3, founding_month=None if i % 8 == 0 else 1 + i % 10,
            funding_stage=["Bootstrapped", "Pre-Seed", "Seed"][i % 3],
            team_size=None if i % 6 == 0 else 2 + i % 12,
            funding_total_eur=None if i % 4 == 0 else float(100000 + i * 85000),
            product_stage=["Prototyp", "MVP", "Pilotkunden", "Marktstart"][i % 4],
            customer_count=None if i % 5 == 0 else i * 2,
            annual_revenue_eur=None if i % 3 == 0 else float(i * 14000),
            traction_notes="Angenommene Pilotaktivität; weder Kunden noch Umsätze sind verifiziert.",
            evidence=[evidence, Evidence(source="Demo-Produktprofil", url=f"{url}/product",
                       finding=f"Fiktive Produktannahme: {product}.", field="product_stage",
                       retrieved_at=evidence.retrieved_at)],
            quality_score=company, company_score=company, market_potential_score=market,
            risk_score=risk_score, overall_score=overall,
            stage_classification=["Pre-Seed", "Seed", "Pre-Seed", "Early Growth", "Seed"][i % 5],
            value_proposition=f"{product.capitalize()} für {['kleine Teams', 'den Mittelstand', 'Großunternehmen', 'spezialisierte Anbieter', 'verteilte Organisationen'][i % 5]}. Ziel: {benefit}.",
            earliness_score=95 - i % 30, confidence_score=40 + i * 7 % 56,
            investment_thesis=f"{name} adressiert {product.lower()}. Die Demo-These: {benefit} "
                             "könnte eine klar messbare Kaufmotivation schaffen. Vor einem Investment "
                             "müssen Zahlungsbereitschaft und wiederholbarer Vertrieb belegt werden.",
            score_drivers=[f"Unternehmensscore {company}/100: simulierte Produkt- und Teamreife.",
                           f"Marktpotenzial {market}/100: angenommene Nachfrage im Zielsegment."],
            risks=[risk.capitalize(), "Wirtschaftlichkeit und Kundenbindung noch nicht verifiziert."],
            open_questions=["Welche Pilotkunden würden einen Jahresvertrag abschließen?",
                            "Wie lange reicht die Finanzierung bis zum nächsten Meilenstein?"],
        ))
    return ResearchResult(leads=sorted(leads, key=lambda x: (-x.overall_score, x.id)))


def demo_search(criteria):
    """Step 1 exposes only identity/contact fields, never the fixture scores."""
    return [RawLead.model_validate(x.model_dump(include=set(RawLead.model_fields)))
            for x in sorted(get_demo_result(criteria.industry).leads, key=lambda x: x.id)][:criteria.limit]


def _fixture(lead):
    return next(x for x in get_demo_result(lead.industry).leads if x.id == lead.id)


def demo_enrich(lead):
    fixture = _fixture(lead)
    extra = set(EnrichedLead.model_fields) - set(RawLead.model_fields)
    return EnrichedLead(**lead.model_dump(), **fixture.model_dump(include=extra))


def demo_evaluate(lead):
    fixture = _fixture(lead)
    extra = set(EvaluatedLead.model_fields) - set(EnrichedLead.model_fields)
    return EvaluatedLead(**lead.model_dump(), **fixture.model_dump(include=extra))
