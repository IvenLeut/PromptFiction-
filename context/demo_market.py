"""One fictional industrial lead with a documented, reproducible market scenario."""
from datetime import date, datetime, timezone

from context.market import research_market
from research_models import (
    Claim, ComparableTransaction, Competitor, Evidence, MarketIntelligence, MarketMeasure,
    MarketSeries, Period,
)

API = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/sbs_ovw_act"
       "?lang=EN&freq=A&indic_sbs=ENT_NR&nace_r2=C&geo=DE&sinceTimePeriod=2021&untilTimePeriod=2023")
AS_OF = datetime(2026, 11, 20, tzinfo=timezone.utc)
SIEMENS = "https://www.siemens.com/en-us/products/industrial-digitalization-services/senseye-predictive-maintenance/"
SCHAEFFLER = "https://www.schaeffler.com/en/investor-relations/events-publications/ir-releases/ir_releases_detail.jsp?id=88164736"
ABB = "https://new.abb.com/process-automation/genix/genix-apm"
HTGF = "https://www.htgf.de/en/zentio-pre-seed/"


def source(name, url, finding, *, document_date=None, status="source_reviewed"):
    return Evidence(source=name, url=url, finding=finding, document_date=document_date,
                    retrieved_at=AS_OF, verification_status=status)


def demo_market(lead):
    eurostat = source("Eurostat SBS", API, "Deutsches verarbeitendes Gewerbe (NACE C), "
                      "Unternehmen: 2021 206391; 2022 204554; 2023 201177.")
    scenario = source("FounderRadar · Demoannahmen", "https://example.org/industrial-16/market-scenario",
                      "Szenario mit 12.000 EUR Jahreserlös pro Kunde, 10 % erreichbarem Anteil "
                      "und einer Kapazität von 30 Kunden. Keine veröffentlichten Produktdaten.",
                      status="assumption")
    competitor_sources = [
        source("Siemens", SIEMENS, "Senseye kombiniert Analytik, Software und Dienste für "
               "werksübergreifende vorausschauende Instandhaltung."),
        source("Schaeffler", SCHAEFFLER, "OPTIME kombiniert Sensorik und Software für "
               "Zustandsüberwachung und Maschinenschmierung."),
        source("ABB", ABB, "Genix APM bündelt anlagenbezogene Analytik, Zustandsüberwachung "
               "und Instandhaltung in einer industriellen IoT-Plattform."),
    ]
    announced = date(2025, 12, 11)
    comp = source("HTGF · Zentio", HTGF, "Zentio hat 1,4 Mio. EUR Pre-Seed für KI-Produktionsplanung "
                  "in der Fertigungsindustrie eingeworben. Die Meldung stammt vom federführenden Investor.",
                  document_date=announced)

    def measure(value, unit, item, methodology, *, year=2023, currency=None, data_type="observed"):
        return MarketMeasure(value=value, unit=unit, currency=currency, geography="Deutschland",
                             period=Period(start_year=year, end_year=year), methodology=methodology,
                             data_type=data_type, evidence_ids=[item.evidence_id])

    history = [measure(number, "Unternehmen", eurostat, "Eurostat SBS, NACE C, ENT_NR", year=year)
               for year, number in ((2021, 206391), (2022, 204554), (2023, 201177))]
    competitors = [
        Competitor(name=name, website=item.url, product=product, segment="Industrielle Instandhaltung",
                   target_customers="Betreiber industrieller Anlagen", development_stage="Commercial",
                   differentiation=differentiation, selection_reason=reason, evidence_ids=[item.evidence_id])
        for item, (name, product, differentiation, reason) in zip(competitor_sources, [
            ("Siemens", "Senseye Predictive Maintenance", "Analytik plus Dienstleistungen",
             "Vergleich für softwarebasierte Auswertung von Maschinendaten"),
            ("Schaeffler", "OPTIME", "Eigene Sensorik und Zustandsüberwachung",
             "Direkte Überschneidung bei drahtloser Zustandserfassung"),
            ("ABB", "Genix Asset Performance Management", "Integration in industrielle IoT-Suite",
             "Alternative im Anlagenmanagement für größere Industriekunden"),
        ])
    ]
    inputs = MarketIntelligence(
        market_definition=Claim(value="Zustandsüberwachung und vorausschauende Instandhaltung in der Fertigung",
                                evidence_ids=[item.evidence_id for item in competitor_sources],
                                origin="analyst_interpretation"),
        target_segment=Claim(value="Deutsche Fertigungsunternehmen mit geeigneten Maschinenparks",
                             evidence_ids=[eurostat.evidence_id, scenario.evidence_id],
                             origin="analyst_interpretation"),
        target_geography=Claim(value="Deutschland", evidence_ids=[eurostat.evidence_id]),
        sizing_inputs={
            "addressable_companies": history[-1],
            "annual_revenue_per_company": measure(12000, "pro Unternehmen und Jahr", scenario,
                                                  "Angenommener Vertragspreis", currency="EUR", data_type="assumption"),
            "serviceable_share": measure(.10, "Anteil", scenario, "Szenario für technisch und vertrieblich erreichbare Firmen",
                                         data_type="assumption"),
            "delivery_capacity": measure(30, "Unternehmen", scenario, "Angenommene jährliche Betreuungskapazität",
                                          data_type="assumption"),
        },
        historical_growth=[MarketSeries(metric="Unternehmensbasis NACE C · keine Umsatzreihe", points=history)],
        growth_drivers=[
            Claim(value="Wirtschaftlicher Anreiz durch vermeidbare Anlagenstillstände",
                  evidence_ids=[competitor_sources[0].evidence_id]),
            Claim(value="Nachrüstbare Sensorik erweitert die technisch erreichbare installierte Basis",
                  evidence_ids=[competitor_sources[1].evidence_id], origin="analyst_interpretation"),
        ],
        competitors=competitors,
        comparison_dimensions=["Nachrüstbarkeit", "Sensorik im Lieferumfang", "Datenintegration", "Zielkundengröße"],
        comparable_transactions=[
            ComparableTransaction(
                company="Zentio", date=announced, sector="Industrielle KI-Software",
                transaction_type="pre_seed", original_source=comp.url,
                transaction_value=measure(1_400_000, "Betrag", comp, "Veröffentlichtes Finanzierungsvolumen",
                                          year=announced.year, currency="EUR"),
                comparability_reason="Angrenzende HTGF-Referenz für industrielle Software und Maschinendaten. "
                                     "Der Anwendungsfall ist Produktionsplanung.",
                evidence_ids=[comp.evidence_id],
            ),
        ],
        research_gaps=["TAM nutzt den gesamten NACE-C-Bestand als Obergrenze. Geeignete Maschinenparks "
                       "und Zahlungsbereitschaft sind noch zu validieren."],
        sources=[eurostat, scenario, *competitor_sources, comp],
    )
    return research_market(lead, inputs)
