from datetime import date
from decimal import Decimal
import sys

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
    # first_signal_date now also exists in RawLead: context may fill a missing
    # date from evidence, while the rest of the sourcing contract stays intact.
    unchanged = set(RawLead.model_fields) - {"first_signal_date"}
    assert lead.model_dump(include=unchanged) == raw.model_dump(include=unchanged)
    assert raw.first_signal_date is None
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


def test_conflicting_vc_and_unknown_status_never_reach_live_scoring():
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
    assert called == ["eligible"]
    assert [lead.id for lead in result.leads] == ["eligible"]
    assert [issue.lead_id for issue in result.issues] == ["conflict", "unknown"]


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
