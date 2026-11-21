"""Scoring of leads sourced from the Förderkatalog (EXIST, no website, no founders), offline.

Regressions from the live run of 2026-11-20 (examples/sourcing/sample_dossiers.json).
"""
from datetime import date, datetime, timezone

from evaluation.engine import _scores, apply_scoring_input, to_dossier
from models import EnrichedLead, Evidence, Grant, Industry, SourceSignal
from scoring import load_config, score_dossier
from scoring_models import Parameter, ScoringEvidence

TAG = date(2026, 11, 20)
FK = "https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFBY0323"
CB = "https://web.archive.org/web/20190701150010/https://www.crunchbase.com/organization/sensai"
IDW = "https://idw-online.de/de/news820044"
CFG = load_config()
REASON = ("EXIST-Forschungstransfer seit 01.10.2024, 598.747,00 €. Branche AI / Software per Regel software_ai. "
          "Flags: early_signal_exist, founding_date_unknown, founders_unknown, pre_founding_team")


def ev(field, url, source="Förderkatalog", day=None, finding="x"):
    return Evidence(field=field, url=url, source=source, finding=finding, source_date=day,
                    retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc))


def sourced(**changes):
    grant = Grant(programme="EXIST-Forschungstransfer", reference="03EFBY0323", amount_eur=598747,
                  start=date(2024, 10, 1), end=date(2026, 7, 31), url=FK)
    fields = dict(
        id="foekat-03efby0323", name="sensAI", description="sensAI: EXIST-Forschungstransfer an der Universität Augsburg.",
        industry=Industry.AI, htgf_sector="digital_tech", country="DE", source_url=FK, prioritization_reason=REASON,
        country_evidence=ev("country", FK, finding="Förderkatalog FKZ 03EFBY0323: Staat Deutschland"),
        signals=[SourceSignal(source="foekat", type="exist_projekt", url=FK, date=date(2024, 10, 1), evidence="FKZ 03EFBY0323")],
        grants=[grant], match_confidence=1.0,
        evidence=[ev("grants", FK, day=date(2024, 10, 1)), ev("first_signal_date", FK, day=date(2024, 10, 1))],
    )
    return EnrichedLead(**(fields | changes))


def run(lead):
    r = score_dossier(to_dossier(lead, CFG), CFG, TAG)
    return r, _scores(r, lead)


# 1 -----------------------------------------------------------------------------------------------
def test_only_real_signals_feed_first_signal_and_why_now():
    noise = [
        ev("in_databases", CB, "Wayback CDX", date(2019, 7, 1)), ev("first_db_date", CB, "Wayback CDX", date(2019, 7, 1)),
        ev("idw_mention", IDW, "idw", date(2023, 9, 5)), ev("idw", IDW, "idw (Erwähnung)", date(2023, 9, 5)),
        ev("founding_statement", IDW, "idw", date(2023, 9, 5)), ev("grants_alt", IDW, "Förderkatalog", date(2020, 1, 1)),
        ev("capital_need", IDW, "Ollama-Zitat aus idw", date(2023, 9, 5)), ev("idw", IDW, "Ollama-Zitat aus idw", date(2023, 9, 5)),
        ev("first_signal_date", IDW, "idw", date(2023, 9, 5)),
    ]
    lead = sourced(evidence=sourced().evidence + noise, in_databases=True, first_db_date=date(2019, 7, 1))
    d = to_dossier(lead, CFG)
    assert {s["datum"] for s in d["signals"]} == {"2024-10-01"}
    r, _ = run(lead)
    assert r["first_signal_date"] == "2024-10-01"
    assert r["why_now"].endswith("jüngstes Signal vor 25 Monaten")
    # a real idw release and a Wayback capture of the own website are signals
    real = sourced(evidence=sourced().evidence + [ev("idw", "https://idw-online.de/de/news9", "idw", date(2025, 3, 1)),
                                                  ev("first_web_capture", "https://web.archive.org/web/2025/x", "Wayback CDX", date(2025, 5, 1))])
    assert {s["datum"] for s in to_dossier(real, CFG)["signals"]} == {"2024-10-01", "2025-03-01", "2025-05-01"}


# 2 -----------------------------------------------------------------------------------------------
def test_founding_year_hint_never_excludes():
    hint = ev("founding_year_mention", IDW, "idw", date(2023, 9, 5), "Das Unternehmen wurde 2023 gegründet.")
    lead = sourced(founding_year_hint=2023, evidence=sourced().evidence + [hint])
    d = to_dossier(lead, CFG)
    assert d["gruendungsdatum"] is None and d["gruendungsjahr_hinweis"] == {"wert": 2023, "quelle": IDW}
    r, _ = run(lead)
    assert r["gruendungsjahr"] == 2023 and r["gruendung_ist_proxy"] is True and r["gruendungsmonat"] is None
    assert r["stage"] == "pre_seed" and "Pressetext" in next(e["aussage"] for e in r["evidence"] if e["dimension"] == "stage")
    assert "Gründungsjahr 2023 nur aus Pressetext, nicht für Ausschluss verwendet" in r["offene_punkte"]

    alt = sourced(founding_year_hint=2022, evidence=sourced().evidence + [hint])  # 47 months before the stichtag
    r, s = run(alt)
    assert r["stage"] == "pre_seed" and r["ausschluss_grund"] == "" and r["gesamt_score"] > 20
    assert r["gruendungsjahr"] == 2022 and r["gruendung_ist_proxy"] is True
    assert not any(x.startswith("Ausschluss") for x in s["risks"])


def test_founding_year_hint_far_before_first_signal_is_ignored():
    """Procado: an unrelated 2013 article gave 2013 for an EXIST project starting 10/2025."""
    # as in the sample: the article is an idw name mention, so it is no signal; the earliest signal is the EXIST start
    old = ev("founding_year_mention", "https://idw-online.de/de/news546496", "idw (Erwähnung)", date(2013, 8, 7), "Gegründet wurde 2013 …")
    procado = sourced(founding_year_hint=2013, evidence=sourced().evidence + [old])
    assert {s["datum"] for s in to_dossier(procado, CFG)["signals"]} == {"2024-10-01"}
    r, _ = run(procado)
    assert r["stage"] == "pre_gruendung" and r["ausschluss_grund"] == ""
    assert r["gruendungsjahr"] == 2024 and r["gruendung_ist_proxy"] is True  # EXIST start, not the press year
    assert any(p.startswith("Gründungsjahr 2013 aus Pressetext liegt mehr als 24 Monate vor dem ersten Signal") for p in r["offene_punkte"])
    # a register/imprint date still excludes
    echt = sourced(founding_year=2013)
    assert run(echt)[0]["stage"] == "zu_spaet"


# 3 -----------------------------------------------------------------------------------------------
def test_low_risk_evidence_is_a_driver_not_a_risk():
    r, s = run(sourced())
    assert not any("Bisherige Förderung" in x for x in s["risks"])
    assert any(x.startswith("Risikomindernd: Bisherige Förderung 598.747 EUR (EXIST-Forschungstransfer)") for x in s["score_drivers"])
    assert any(x.startswith("Dünne Datenlage") for x in s["risks"])  # 80 points >= 50
    for x in s["risks"]:
        e = next(e for e in r["evidence"] if x.startswith(e["aussage"]))
        assert e["punkte"] >= CFG["texte"]["risiko_ab"] * 100


# 4 -----------------------------------------------------------------------------------------------
def test_unclassified_industry_is_not_a_sector():
    for reason in ("EXIST. Flags: early_signal_exist, industry_unclassified",
                   "EXIST.\nHinweise: founders_unknown, industry_unclassified",
                   "EXIST. Branche nicht klassifiziert, Standard Industrial / DeepTech."):
        lead = sourced(htgf_sector=None, industry=Industry.INDUSTRIAL, prioritization_reason=reason)
        assert to_dossier(lead, CFG)["branche"] is None and run(lead)[0]["branche"] is None
    marked_signal = sourced(htgf_sector=None, prioritization_reason="EXIST",
                            signals=[SourceSignal(source="foekat", type="exist_projekt", url=FK, date=date(2024, 10, 1),
                                                  evidence="FKZ 03EFBY0323; industry_unclassified")])
    assert to_dossier(marked_signal, CFG)["branche"] is None
    # classified or unmarked: unchanged
    assert to_dossier(sourced(), CFG)["branche"] == "digital_tech"
    assert to_dossier(sourced(htgf_sector=None, prioritization_reason="EXIST"), CFG)["branche"] == "digital_tech"
    demo = sourced(htgf_sector=None, is_demo=True, prioritization_reason="industry_unclassified")
    assert to_dossier(demo, CFG)["branche"] == "digital_tech"


# 5 -----------------------------------------------------------------------------------------------
def test_exist_without_founders_reads_sensibly():
    lead = sourced(grants=[Grant(programme="EXIST-Forschungstransfer", amount_eur=1029852, start=date(2025, 10, 1),
                                 end=date(2026, 9, 30), url=FK)],
                   signals=[SourceSignal(source="foekat", type="exist_projekt", url=FK, date=date(2025, 10, 1), evidence="FKZ")],
                   evidence=[ev("grants", FK, day=date(2025, 10, 1)), ev("in_databases", "https://web.archive.org/cdx/x", "Wayback CDX")],
                   in_databases=False)
    r, _ = run(lead)
    # 59: Vollzeit (EXIST) + Forschungsteam-Proxy des Forschungstransfers (scoring_config: komplementaer.forschungsteam)
    assert r["team_score"] == 59.0 and r["confidence"] < CFG["texte"]["hypothese_min_confidence"]
    assert r["investmenthypothese"].startswith("Datenlage zu dünn für eine Hypothese")
    assert "Wir investieren" not in r["investmenthypothese"]
    assert r["why_now"] == ("Noch vor der Gründung; EXIST-Forschungstransfer endete 09/2026; "
                            "kein archiviertes Crunchbase-/Dealroom-Profil (Wayback); jüngstes Signal vor 13 Monaten")
    future = lead.model_copy(update={"grants": [lead.grants[0].model_copy(update={"end": date(2027, 9, 30)})]})
    assert run(future)[0]["why_now"] == ("Noch vor der Gründung; EXIST-Forschungstransfer endet 09/2027; "
                                         "kein archiviertes Crunchbase-/Dealroom-Profil (Wayback); jüngstes Signal vor 13 Monaten")


# 6 -----------------------------------------------------------------------------------------------
def test_funding_evidence_names_the_programme_and_ended_grant_in_why_now():
    stip = sourced(grants=[Grant(programme="EXIST-Gründungsstipendium", amount_eur=135000, start=date(2025, 10, 1),
                                 end=date(2026, 9, 30), url=FK)],
                   signals=[SourceSignal(source="foekat", type="exist_projekt", url=FK, date=date(2025, 10, 1), evidence="FKZ")])
    r, _ = run(stip)
    fin = next(e for e in r["evidence"] if e["kriterium"] == "finanzierung")
    assert fin["aussage"] == "Bisherige Förderung 135.000 EUR (EXIST-Gründungsstipendium)" and fin["punkte"] == 40.0
    assert "EXIST-Gründungsstipendium endete 09/2026" in r["why_now"]
    ft = next(e for e in run(sourced())[0]["evidence"] if e["kriterium"] == "finanzierung")
    assert ft["aussage"] == "Bisherige Förderung 598.747 EUR (EXIST-Forschungstransfer)" and ft["punkte"] == 30.0
    # ended more than exist_nachlauf_monate ago: no longer mentioned
    alt = stip.model_copy(update={"grants": [stip.grants[0].model_copy(update={"start": date(2024, 1, 1), "end": date(2024, 12, 31)})]})
    assert "endete" not in run(alt)[0]["why_now"]


# 7 -----------------------------------------------------------------------------------------------
def test_usable_public_grant_does_not_duplicate_funding():
    from scoring_input import build_scoring_input
    lead = sourced()
    scoring = build_scoring_input(lead, as_of=TAG)
    beleg = ScoringEvidence(url=FK, excerpt="EXIST-Forschungstransfer 598.747 EUR", document_date=date(2024, 10, 1),
                            kind="source_excerpt", subject_lead_id=lead.id)
    grant = Parameter(value="received", status="usable", rule="test", provenance="source_reported", evidence_ids=[beleg.stable_id()])
    scoring = scoring.model_copy(update={"public_grant": grant, "evidence": scoring.evidence | {beleg.stable_id(): beleg}})
    d = apply_scoring_input(to_dossier(lead, CFG), scoring)
    assert d["foerderung"] == [{"programm": "EXIST-Forschungstransfer", "summe_eur": 598747, "start": "2024-10-01",
                                "ende": "2026-07-31", "quelle": FK, "kennzeichen": "03EFBY0323",
                                "empfaenger": None, "ausfuehrende_stelle": None, "thema": None}]
    assert sum(e["kriterium"] == "finanzierung" and e["url"] is not None for e in score_dossier(d, CFG, TAG)["evidence"]) == 1
