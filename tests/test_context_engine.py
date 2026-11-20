"""Integration of context.engine.enrich with injected lookups (offline)."""
from datetime import date

from context.engine import default_lookups, enrich, field_terms
from context.lookup import Lookup
from evaluation.engine import evaluate, to_dossier
from models import Evidence, FounderProfile, Grant, Industry, Partner, Patent, RawLead, SourceSignal
from scoring import load_config

U = "https://example.org/"


def make_lead(**changes):
    fields = dict(id="t", name="Testwerk", description="Testwerk entwickelt Elektronenspinresonanz-Sensorik auf Chipbasis für die Materialanalyse.",
                  industry=Industry.INDUSTRIAL, htgf_sector="industrial_deep_tech", country="DE", location="Stuttgart",
                  source_url=U + "fund", founders=["Kim Muster", "Alex Beispiel"], website=U,
                  country_evidence=Evidence(source="Sourcing", url=U + "fund", finding="Sitz in Stuttgart"),
                  signals=[SourceSignal(source="foekat", type="exist_projekt", url=U + "fk", date=date(2025, 4, 1), evidence="FKZ 03EFTEST01 Testwerk")])
    return RawLead(**(fields | changes))


def fake_lookups(calls):
    def imprint(website, *, cache, fetch=None):
        calls.append("imprint")
        l = Lookup(signals=[SourceSignal(source="Impressum", type="impressum", url=U + "impressum", evidence="Testwerk UG (haftungsbeschränkt) i.G.")])
        l.add("imprint_url", U + "impressum", url=U + "impressum", finding="Impressum", source="Impressum")
        l.add("legal_form", "UG (haftungsbeschränkt)", url=U + "impressum", finding="Testwerk UG (haftungsbeschränkt) i.G.", source="Impressum")
        l.add("in_formation", True, url=U + "impressum", finding="i.G.", source="Impressum")
        l.add("contact_email", "info@example.org", url=U + "impressum", finding="info@example.org", source="Impressum")
        return l

    def grants(name, *, institution, reference, cache, fetch=None):
        calls.append(("grants", institution, reference))
        g = Grant(programme="EXIST-Forschungstransfer", reference="03EFTEST01", recipient="Universität Stuttgart, Universität Stuttgart - Institut X",
                  amount_eur=900000, start=date(2025, 4, 1), end=date(2026, 9, 30), url=U + "fk")
        l = Lookup(fields={"match_confidence": 0.9, "institution": "Universität Stuttgart"},
                   signals=[SourceSignal(source="Förderkatalog", type="exist_projekt", url=U + "fk", date=date(2025, 4, 1), evidence="Thema: Testwerk")])
        l.evidence.append(Evidence(field="grants", url=U + "fk", finding="EXIST", source="Förderkatalog", source_date=date(2025, 4, 1)))
        return [g], l

    def web_history(website, name, *, cache, fetch=None):
        calls.append("web_history")
        l = Lookup()
        l.add("first_web_capture", date(2025, 6, 1), url="https://web.archive.org/cdx/x", finding="Erste Aufnahme", source="Wayback CDX", source_date=date(2025, 6, 1))
        l.add("in_databases", False, url="https://web.archive.org/cdx/y", finding="kein Profil", source="Wayback CDX")
        return l

    def idw(name, *, institution, founders, cache, fetch=None):
        calls.append(("idw", institution, tuple(founders)))
        l = Lookup(signals=[SourceSignal(source="idw", type="idw", url=U + "news1", date=date(2025, 5, 2), evidence="Testwerk: Pilotanlage mit Partner AG")])
        l.evidence.append(Evidence(field="idw", url=U + "news1", finding="Testwerk startet Pilotanlage", source="idw", source_date=date(2025, 5, 2)))
        l.evidence.append(Evidence(field="founding_year_mention", url=U + "news1", finding="Testwerk wurde 2025 gegründet.", source="idw", source_date=date(2025, 5, 2)))
        l.fields["founding_year_hint"] = 2025
        return l

    def author(name, *, institution, field_terms, cache, fetch=None):
        calls.append(("author", name, institution, tuple(field_terms)))
        if name != "Kim Muster":
            return None, Lookup(errors=["openalex: kein Treffer für %s" % name])
        p = FounderProfile(name=name, institution="Universität Stuttgart", openalex_url="https://openalex.org/A1", works_total=20,
                           works_in_field=5, match_confidence=0.9, source_url="https://openalex.org/A1")
        l = Lookup()
        l.evidence.append(Evidence(field="founder_profiles", url="https://openalex.org/A1", finding="OpenAlex", source="OpenAlex"))
        return p, l

    def classify(name, signals, *, model, cache, ask=None, founders=()):
        calls.append(("classify", len(signals), model, tuple(founders)))
        l = Lookup()
        l.fields["partners"] = [Partner(name="Partner AG", kind="pilot", url=U + "news1")]
        l.fields["patents"] = [Patent(status="patent_angemeldet", url=U + "news1")]
        l.add("ip_status", "patent_angemeldet", url=U + "news1", finding="zum Patent angemeldet", source="idw")
        l.add("product_stage", "pilot", url=U + "news1", finding="Pilotanlage", source="idw")
        l.add("product_type", "hardware_software", url=U, finding="Sensorchip mit Software", source="Website")
        return l

    def broken(*a, **k):
        calls.append("patents")
        raise RuntimeError("boom")

    return {"cache": None, "model": "qwen-test", "imprint": imprint, "grants": grants, "web_history": web_history, "idw": idw,
            "author": author, "classify": classify, "patents": broken}


def test_enrich_merges_all_lookups_in_order():
    calls = []
    lead = enrich(make_lead(), load_pages=lambda _: [], lookups=fake_lookups(calls))
    names = [c if isinstance(c, str) else c[0] for c in calls]
    assert names[:4] == ["imprint", "grants", "web_history", "idw"] and names[-1] == "classify"
    # the grant recipient is shortened to the institution before it reaches idw and OpenAlex
    assert next(c for c in calls if c[0] == "grants")[2] == "03EFTEST01"
    assert next(c for c in calls if c[0] == "author")[2] == "Universität Stuttgart"
    assert next(c for c in calls if c[0] == "classify")[1] >= 3 and "Kim Muster" in next(c for c in calls if c[0] == "classify")[3]
    assert lead.legal_form == "UG (haftungsbeschränkt)" and lead.in_formation is True and lead.imprint_email == "info@example.org"
    assert lead.contact_email is None  # step-1 field is never rewritten
    assert lead.grants[0].amount_eur == 900000 and lead.match_confidence == 0.9 and lead.funding_status == "non_vc_funded"
    assert lead.first_web_capture == date(2025, 6, 1) and lead.in_databases is False
    assert lead.founding_year_hint == 2025
    assert [p.kind for p in lead.partners] == ["pilot"] and lead.ip_status == "patent_angemeldet" and len(lead.patents) == 1
    assert lead.product_stage == "pilot" and lead.product_type == "hardware_software"
    assert [p.name for p in lead.founder_profiles] == ["Kim Muster", "Alex Beispiel"]
    assert lead.founder_profiles[0].works_in_field == 5 and lead.founder_profiles[1].openalex_url is None
    assert lead.enrichment_sources == ["imprint", "grants", "web_history", "idw", "author", "classify"]
    assert any(e.startswith("patents: RuntimeError") for e in lead.enrichment_errors)
    assert any("Alex Beispiel" in e for e in lead.enrichment_errors)
    assert "Welcher Produktstand ist heute nachweisbar?" not in lead.research_questions
    assert lead.first_signal_date == date(2025, 4, 1)
    assert {e.field for e in lead.evidence} >= {"legal_form", "grants", "first_web_capture", "in_databases", "ip_status", "product_stage", "founding_year_mention"}


def test_rules_win_over_classifier_and_demo_leads_skip_lookups():
    calls = []
    website = SourceSignal(source="Website", type="website", url=U + "produkt", evidence="Produktreife: MVP")
    lead = enrich(make_lead(), load_pages=lambda _: [website], lookups=fake_lookups(calls))
    assert lead.product_stage == "mvp"
    demo = enrich(make_lead(is_demo=True, id="d"), lookups=fake_lookups(calls := []))
    assert calls == [] and demo.enrichment_sources == [] and demo.grants == []


def test_dossier_carries_every_enriched_field_with_source():
    lead = enrich(make_lead(), load_pages=lambda _: [], lookups=fake_lookups([]))
    d = to_dossier(lead, load_config())
    assert d["rechtsform"] == {"wert": "UG (haftungsbeschränkt) i.G.", "quelle": U + "impressum"}
    assert d["email"] == {"wert": "info@example.org", "quelle": U + "impressum"}
    # a press-sentence year is only a hint, never the founding date (see tests/test_scoring_sourced_leads.py)
    assert d["gruendungsdatum"] is None and d["gruendungsjahr_hinweis"] == {"wert": 2025, "quelle": U + "news1"}
    assert d["foerderung"][0]["summe_eur"] == 900000 and d["foerderung"][0]["quelle"] == U + "fk"
    assert d["team"][0]["papers_im_feld"] == 5 and d["team"][0]["openalex"] == "https://openalex.org/A1"
    assert d["partner"] == [{"name": "Partner AG", "typ": "pilot", "quelle": U + "news1"}]
    assert d["ip"] == {"wert": "patent_angemeldet", "quelle": U + "news1"}
    assert d["reifegrad"] == {"wert": "pilot", "quelle": U + "news1"} and d["produkt_typ"]["wert"] == "hardware_software"
    assert d["in_databases"] is False and d["in_databases_quelle"].startswith("https://web.archive.org")
    assert {s["typ"] for s in d["signals"]} >= {"exist_projekt", "idw", "wayback"}
    r = evaluate(lead)
    assert r.stage_classification == "Pre-Seed" and r.confidence_score > 60
    # 900 k€ funding is 25 risk points (< texte.risiko_ab), so it reduces risk and is listed as a driver
    assert any(x.startswith("Risikomindernd: Bisherige Förderung 900.000 EUR") for x in r.score_drivers)
    assert not any("900.000 EUR" in x for x in r.risks) and any("Papers" in x for x in r.score_drivers)


def test_field_terms_and_default_lookups():
    terms = field_terms(make_lead())
    assert "Elektronenspinresonanz-Sensorik" in terms and all(t.lower() not in {"entwickelt", "chipbasis"} or t == "Chipbasis" for t in terms)
    from context.cache import NoCache
    lookups = default_lookups(cache=NoCache())
    assert lookups["patents"] is None and callable(lookups["imprint"]) and callable(lookups["grants"])
    assert callable(default_lookups(cache=NoCache(), patents=True)["patents"])


def test_default_lookups_without_cache_never_opens_a_file(tmp_path, monkeypatch):
    from context.cache import NoCache
    monkeypatch.chdir(tmp_path)
    assert isinstance(default_lookups(cache=None)["cache"], NoCache)
    assert not (tmp_path / ".cache").exists()


def test_catalogue_signal_drops_person_names():
    unit = "Ausführende Stelle: Universität Augsburg, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau"
    signal = SourceSignal(source="foekat", type="exist_projekt", url=U + "fk", date=date(2025, 4, 1),
                          evidence="Förderkennzeichen: 03EFTEST01\nFörderempfänger: Universität Augsburg\n" + unit)
    lead = enrich(make_lead(signals=[signal]), light=True)
    assert lead.grants[0].recipient == "Universität Augsburg"
    assert not any("Musterfrau" in e.finding for e in lead.evidence if e.field == "grants")
