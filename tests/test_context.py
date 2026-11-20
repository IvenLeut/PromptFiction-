from datetime import date
from decimal import Decimal
import sys

import pytest

from context.__main__ import main
from context.engine import enrich
from context.web import CompanyPage
from evaluation.valuation import ValuationAssumptions, value_lead
from models import ContextResult, EnrichedLead, Evidence, Industry, RawLead, SourceSignal
from pipeline import collect_context, evaluate_context


def make_lead(**changes):
    url = "https://example.org/"
    fields = dict(
        id="demo-integration", name="Testfirma", description="Produktbeschreibung",
        industry=Industry.AI, country="DE", source_url=url, founders=["Kim Muster"],
        country_evidence=Evidence(source="Sourcing", url=url, finding="Sitz in Berlin"),
    )
    return RawLead(**(fields | changes))


def test_context_combines_sourcing_and_website_with_evidence():
    signal = SourceSignal(
        source="Uni", type="ausgruendung", date=date(2026, 9, 1), url="https://example.org/uni",
        evidence="Kim Muster – Hintergrund: Promotion in Informatik.\nProblem: Lange Prüfzeiten.",
    )
    website = SourceSignal(
        source="Website", type="website", url="https://example.org/team",
        evidence="Kim Muster – CTO\nTarget customers\nIndustriebetriebe\nProduct stage: MVP",
    )
    raw = make_lead(website="https://example.org/", has_vc=False, signals=[signal])
    result = collect_context([raw], use_mock=False, enricher=lambda lead: enrich(
        lead, load_pages=lambda _: [website],
    ))
    assert not result.issues
    lead = result.leads[0]
    assert lead.model_dump(include=set(RawLead.model_fields)) == raw.model_dump()
    assert lead.founder_profiles[0].role == "CTO"
    assert lead.founder_profiles[0].qualifications == "Promotion in Informatik."
    assert lead.customer_problem == "Lange Prüfzeiten."
    assert lead.target_customers == "Industriebetriebe"
    assert lead.product_stage == "mvp"
    assert lead.vc_status == "reported_none"
    assert lead.funding_status == "unknown"
    assert lead.first_signal_date == signal.date
    assert any(item.field == "customer_problem" and item.source_date == signal.date
               and item.url == signal.url for item in lead.evidence)


def test_conflicting_vc_never_reaches_live_scoring_but_unknown_does():
    signal = SourceSignal(source="Firma", type="press", url="https://example.org/press",
                          evidence="Funding status: VC-backed\nProduct stage: Prototyp\nProduct stage: MVP")
    conflict = enrich(make_lead(id="conflict", has_vc=False, signals=[signal]))
    unknown = enrich(make_lead(id="unknown"))
    eligible = enrich(make_lead(id="eligible", has_vc=False))
    called = []

    def evaluator(lead):
        called.append(lead.id)
        return dict(**lead.model_dump(), overall_score=None, company_score=None,
                    market_potential_score=None, risk_score=None, stage_classification="Unbekannt",
                    value_proposition="Test", investment_thesis="")

    assert conflict.vc_status == "conflicting"
    assert conflict.product_stage is None
    assert EnrichedLead.model_validate_json(conflict.model_dump_json()) == conflict
    result = evaluate_context([conflict, unknown, eligible], use_mock=False, evaluator=evaluator)
    assert called == ["unknown", "eligible"]
    assert [lead.id for lead in result.leads] == ["eligible", "unknown"]
    assert [issue.lead_id for issue in result.issues] == ["conflict"]
    assert "Welche Investoren sind bereits beteiligt?" in unknown.research_questions


def test_html_backs_extracted_claims_and_ignores_scripts():
    page = CompanyPage()
    page.feed(
        "<h2>Produktreife</h2><p>Laborprototyp</p>"
        "<script>Produktreife: MVP</script><p>Kim Muster – <b>CTO</b></p>"
    )
    signal = SourceSignal(source="Website", type="website", url="https://example.org/",
                          evidence="\n".join(page.lines))
    lead = enrich(make_lead(signals=[signal]))
    assert lead.product_stage == "labor_prototyp"
    assert lead.founder_profiles[0].role == "CTO"


def test_offline_command_exports_valid_context_result(tmp_path, monkeypatch):
    source = tmp_path / "leads.json"
    output = tmp_path / "dossiers.json"
    lead = make_lead(website="https://example.org/", has_vc=False)
    leads = [lead, *(lead.model_copy(update={"id": str(i)}) for i in range(7))]
    source.write_text("[" + ",".join(item.model_dump_json() for item in leads) + "]", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["context", str(source), str(output), "--offline"])
    main()
    result = ContextResult.model_validate_json(output.read_bytes())
    assert [item.id for item in result.leads] == [lead.id, "0", "1", "2", "3"]
    assert result.leads[0].id == lead.id
    assert result.leads[0].vc_status == "reported_none"


def test_quotes_require_source_and_terms_feed_vc_method():
    signal = SourceSignal(
        source="Presse", type="press", url="https://example.org/news",
        evidence="Unser Vertrieb läuft über Integratoren.\nRundengröße: 1,2 Mio. EUR\n"
                 "Geforderte Pre-Money-Bewertung: 4.000.000 EUR",
    )
    lead = enrich(make_lead(has_vc=False, signals=[signal]), extract_quotes=lambda *_: [
        ("sales", "Unser Vertrieb läuft über Integratoren.", signal),
        ("competition", "Ein erfundener Wettbewerber", signal),
    ])
    assert lead.sales == "Unser Vertrieb läuft über Integratoren."
    assert lead.competition is None
    assert lead.round_size_eur == 1_200_000
    assert lead.asking_pre_money_eur == 4_000_000
    assumptions = ValuationAssumptions(vc_method={
        "exit_equity_value_eur": 50_000_000, "future_dilution": "0.25", "target_moic": 5,
    })
    result = value_lead(lead, assumptions)
    assert result.vc_max_pre_money_eur == Decimal(6_300_000)
    assert result.vc_price_headroom_eur == Decimal(2_300_000)
    assert result.scorecard_pre_money_eur is None
    assert value_lead(lead.model_copy(update={"asking_pre_money_eur": None}),
                      assumptions).vc_max_pre_money_eur is None


def test_scorecard_uses_explicit_benchmark_and_relative_scores():
    names = ("team", "market", "technology", "competition", "sales", "capital_need")
    weights = ("0.25", "0.25", "0.2", "0.1", "0.1", "0.1")
    factors = {name: {"weight": weight, "relative_score": "1.1", "rationale": "Testbeleg"}
               for name, weight in zip(names, weights)}
    assumptions = ValuationAssumptions(scorecard={
        "benchmark_pre_money_eur": 2_000_000, "benchmark_source": "Testbenchmark",
        "factors": factors,
    })
    assert value_lead(enrich(make_lead(has_vc=False)), assumptions).scorecard_pre_money_eur == 2_200_000
    assert value_lead(enrich(make_lead()), assumptions).scorecard_pre_money_eur is None


# --- context.web: parked domains and the page cache --------------------------------------------------

def test_parked_domain_fixture_is_rejected():
    """Regression (Siderogain): siderogain.de serves a domain-parking page whose "Buy now" line was read as
    product_stage=am_markt. Parked pages must not yield any text."""
    import pytest
    from pathlib import Path
    from context.web import is_parked, parse_page
    html = (Path(__file__).parent / "fixtures" / "context" / "web_parked_domain.html").read_text("utf-8")
    with pytest.raises(ValueError, match="Geparkte Domain"):
        parse_page(html)
    assert is_parked(["Domain for sale", "Siderogain.de"])
    assert is_parked(["This domain is parked free, courtesy of Sedo"])
    assert not is_parked(["Wir bauen Sensoren.", "Jetzt kaufen", "Make the most of your data"])
    normal = parse_page("<p>Wir bauen Sensoren.</p><p>Jetzt bestellen</p>")
    assert normal.lines == ["Wir bauen Sensoren.", "Jetzt bestellen"]


def test_web_fetch_memoises_pages_and_misses(tmp_path, monkeypatch):
    import pytest
    from context import web
    from context.cache import Cache
    cache = Cache(tmp_path / "c.db")
    calls = []

    def fake_fetch(url, site):
        calls.append(url)
        if url.endswith("/dead"):
            raise OSError("connection refused")
        if url.endswith("/parked"):
            raise ValueError(web.PARKED_ERROR)
        return url.replace("/start", "/final"), web.parse_page("<p>Hallo Welt</p><a href='/team'>Team</a>")

    monkeypatch.setattr(web, "_fetch", fake_fetch)
    final, page = web.fetch("https://example.org/start", "example.org", cache=cache)
    assert final == "https://example.org/final" and page.lines == ["Hallo Welt", "Team"] and page.links == ["/team"]
    again_final, again = web.fetch("https://example.org/start", "example.org", cache=cache)
    by_final, _ = web.fetch("https://example.org/final", "example.org", cache=cache)
    assert (again_final, again.lines, again.links) == (final, page.lines, page.links) and by_final == final
    assert calls == ["https://example.org/start"]                       # requested and final URL both served from cache
    with pytest.raises(OSError):
        web.fetch("https://example.org/dead", "example.org", cache=cache)
    with pytest.raises(ValueError, match="connection refused"):         # the miss is memoised as an error
        web.fetch("https://example.org/dead", "example.org", cache=cache)
    with pytest.raises(ValueError, match="Geparkte Domain"):
        web.fetch("https://example.org/parked", "example.org", cache=cache)
    with pytest.raises(ValueError, match="Geparkte Domain"):
        web.fetch("https://example.org/parked", "example.org", cache=cache)
    assert calls == ["https://example.org/start", "https://example.org/dead", "https://example.org/parked"]
    keys = sorted(k for (k,) in cache._db().execute("SELECT key FROM cache"))
    assert len(keys) == 4 and all(k.startswith("web:") and len(k) == 44 for k in keys)
    # without a cache every call goes to the network, and the signature without cache still works
    monkeypatch.setattr(web, "_fetch", lambda url, site: (url, web.parse_page("<p>Seite</p>")))
    assert web.fetch("https://example.org/", "example.org")[1].lines == ["Seite"]
    assert [s.evidence for s in web.company_pages("https://example.org/", cache=cache)] == ["Seite"]
    assert web.original_page("https://example.org/x", cache=cache).evidence == "Seite"


def test_company_pages_yield_nothing_for_a_parked_site(monkeypatch):
    from context import web
    monkeypatch.setattr(web, "_fetch", lambda url, site: (_ for _ in ()).throw(ValueError(web.PARKED_ERROR)))
    assert list(web.company_pages("https://parked.example.org/")) == []
    assert web.original_page("https://parked.example.org/") is None


def test_context_v2_preserves_legacy_evidence_and_distinguishes_traction():
    old = Evidence.model_validate({
        "dimension": "Team", "kriterium": "Erfahrung", "aussage": "Quellenangabe",
        "url": "https://example.org/", "datum": "2025-02-03", "punkte": 2,
    })
    assert old.finding == old.aussage and old.punkte == 2
    assert old.document_date == date(2025, 2, 3)
    assert Evidence.model_validate_json(old.model_dump_json()).evidence_id == old.evidence_id
    signal = SourceSignal(
        source="Unternehmen", type="press", url="https://example.org/press", date=date(2025, 3, 1),
        evidence="Kim Muster – Erfahrung mit dem Kundenproblem: Leitete Maschinenwartung.\n"
                 "Gründungsdatum: 2025-02-03\n"
                 "Zahlende Kunden: A\n"
                 "Bezahlte Pilotprojekte: B\nUnbezahlte Pilotprojekte: C\n"
                 "LOI: D\nForschungspartner: E\nÖffentliche Förderung: Antrag geplant\n"
                 "Jahresumsatz 2025: 120.000 EUR\nUmsatzwachstum 2025: 12,5 %",
    )
    raw = make_lead(website="https://example.org/", founding_year=2024, signals=[signal], country_evidence=old)
    enriched = enrich(raw, light=True, load_pages=lambda _: pytest.fail("unexpected network access"))
    assert enriched.model_dump(include=set(RawLead.model_fields)) == raw.model_dump()
    context = enriched.context_v2
    assert context.company.founding_date_status == "conflicting"
    assert context.company.founding_date is None
    assert context.founders[0].customer_problem_experience.value == "Leitete Maschinenwartung."
    traction = context.traction
    assert traction.paid_customers[0].value == "A"
    assert traction.paid_pilots[0].value == "B"
    assert traction.unpaid_pilots[0].value == "C"
    assert traction.lois[0].value == "D"
    assert traction.research_partners[0].value == "E"
    assert traction.reported_metrics["revenue_growth"][0].value == 12.5
    assert enriched.annual_revenue_eur == 120000
    assert not context.funding.rounds and context.funding.status == "unknown"
    assert context.funding.public_grants[0].value == "Antrag geplant"
    assert traction.paid_customers[0].evidence_ids[0] in {item.evidence_id for item in enriched.evidence}


def test_demo_market_has_reproducible_sizing_growth_and_original_sources():
    from models import SearchCriteria
    from pipeline import run_pipeline

    run = run_pipeline(SearchCriteria(industry=Industry.INDUSTRIAL))
    assert not run.result.issues
    lead = next(lead for lead in run.result.leads if lead.id == "industrial-16")
    market = lead.context_v2.market_intelligence
    assert (market.tam.value, market.sam.value, market.som.value) == (2_414_124_000, 241_404_000, 360_000)
    assert len(market.competitors) == 3
    assert market.historical_growth[0].cagr.value < 0
    assert not market.forecast_growth
    assert market.comparable_transactions[0].transaction_value.value == 1_400_000
    assert market.comparable_transactions[0].ev_revenue is None
    assert market.comparable_transactions[0].ev_ebitda is None
    assert set(market.tam.evidence_ids) <= {item.evidence_id for item in market.sources}
    assert market.sizing_inputs["annual_revenue_per_company"].data_type == "assumption"


def test_targeted_market_source_claim_links_and_missing_numbers():
    from context.market import research_market
    from context.market_sources import gather_market_sources
    from research_models import Claim, MarketIntelligence

    url = "https://example.org/industry"
    signal = SourceSignal(source="Marktstudie", type="market", url=url,
                          evidence="Marktdefinition: Industrieüberwachung\nWachstumstreiber: Nachrüstbarkeit\n"
                                   "TRL: 6 – Demonstration in relevanter Umgebung")
    inputs = gather_market_sources(MarketIntelligence(), [url], load_page=lambda _: signal)
    raw_context = enrich(make_lead(), light=True)
    market = research_market(raw_context, inputs).context_v2.market_intelligence
    assert market.market_definition.value == "Industrieüberwachung"
    assert market.sector_metrics.technology_readiness.level == 6
    assert market.tam is None and market.research_gaps
    inputs.market_definition = Claim(value="Unbelegt", evidence_ids=["missing"])
    with pytest.raises(ValueError, match="Unbekannte Evidence-IDs"):
        research_market(raw_context, inputs)


def test_market_cli_targets_one_lead(tmp_path, monkeypatch):
    source = tmp_path / "leads.json"
    market = tmp_path / "market.json"
    output = tmp_path / "dossiers.json"
    leads = [make_lead(id=lead_id) for lead_id in ("first", "selected")]
    source.write_text("[" + ",".join(lead.model_dump_json() for lead in leads) + "]", encoding="utf-8")
    market.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "context", str(source), str(output), "--offline", "--lead", "selected", "--market-input", str(market),
    ])
    main()
    result = ContextResult.model_validate_json(output.read_bytes())
    assert [lead.id for lead in result.leads] == ["selected"]
    assert result.leads[0].context_v2.research_status.market == "partial"
