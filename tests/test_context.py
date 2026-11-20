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
