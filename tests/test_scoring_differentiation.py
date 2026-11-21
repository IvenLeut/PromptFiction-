"""T2: Scoring differenziert Förderkatalog-Leads, schließt alte Firmen aus und filtert Noise (offline).

Befunde 21.11.2026: 733 Leads lagen bei 48,7–53,7 (6 Werte); kiutra (gegr. 2018, in DBs) war `seed` statt `zu_spaet`.
"""
import copy
import re
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from evaluation.engine import to_dossier
from models import EnrichedLead, Evidence, Grant, Industry, SourceSignal
from scoring import load_config, score_all, score_dossier

TAG = date(2026, 11, 20)
CFG = load_config()
ROOT = Path(__file__).resolve().parent.parent
FK = "https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=%s"
IDW = "https://idw-online.de/de/news797717"


def katalog_text(fkz, programm, thema, empf, stelle, von, bis, summe):
    return ("Förderkennzeichen: %s\nProgramm: %s\nThema: %s\nFörderempfänger: %s\nAusführende Stelle: %s\n"
            "Laufzeit: %s bis %s\nFördersumme: %s EUR" % (fkz, programm, thema, empf, stelle, von, bis, summe))


def lead(fkz="03EFBY0001", programm="EXIST-Forschungstransfer", thema="QuantSense", summe=1_000_000,
         start=date(2025, 6, 1), ende=date(2027, 1, 31),
         empf="Technische Universität München, Muenchen, Bayern",
         stelle="Technische Universität München - Lehrstuhl für Physik der Quantensensorik, Garching b. München, Bayern",
         **changes):
    url = FK % fkz
    text = katalog_text(fkz, programm, thema, empf, stelle, start.strftime("%d.%m.%Y"), ende.strftime("%d.%m.%Y"), summe)
    fields = dict(
        id="foekat-" + fkz.lower(), name=thema, description="„%s“ – Projekt im Programm %s." % (thema, programm),
        industry=Industry.INDUSTRIAL, country="DE", source_url=url,
        country_evidence=Evidence(source="Förderkatalog", url=url, finding="Staat Deutschland", field="country",
                                  retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc)),
        signals=[SourceSignal(source="Förderkatalog", type="exist_projekt", url=url, date=start, evidence=text)],
        grants=[Grant(programme=programm, reference=fkz, recipient=empf, amount_eur=summe, start=start, end=ende, url=url)],
    )
    return EnrichedLead(**(fields | changes))


def run(x, tag=TAG):
    return score_dossier(to_dossier(x, CFG), CFG, tag)


def teil(r, dim, krit):
    return r["teilwerte"][dim][krit]


# --- 1. Förderkatalog-Felder kommen an und zählen ------------------------------------------------------------------
def test_catalogue_fields_reach_the_dossier():
    d = to_dossier(lead(), CFG)
    f = d["foerderung"][0]
    assert f["kennzeichen"] == "03EFBY0001" and f["thema"] == "QuantSense"
    assert f["ausfuehrende_stelle"].startswith("Technische Universität München - Lehrstuhl für Physik")


def test_forschungstransfer_beats_generic_stipendium():
    ef = run(lead())
    eg = run(lead(fkz="03EGNW0002", programm="EXIST-Gründungsstipendium", thema="ShopHelfer", summe=60_000,
                  start=date(2024, 3, 1), ende=date(2025, 2, 28), empf="Hochschule Niederrhein, Krefeld, Nordrhein-Westfalen",
                  stelle="Hochschule Niederrhein, Krefeld, Nordrhein-Westfalen"))
    assert ef["gesamt_score"] - eg["gesamt_score"] >= 8
    assert teil(ef, "marktpotenzial", "tech_tiefe")["belegt"] and teil(ef, "marktpotenzial", "tech_tiefe")["proxy"]
    for r in (ef, eg):  # jeder neue Teilwert hat die Katalogseite als Beleg
        for e in r["evidence"]:
            if e["kriterium"] in ("forschungsumfeld", "timing", "tech_tiefe", "skalierbarkeit", "komplementaer") and e["url"]:
                assert e["url"].startswith("https://foerderportal.bund.de/")


def test_institution_classes():
    werte = {}
    for name, empf in (("aussen", "Fraunhofer-Gesellschaft zur Förderung der angewandten Forschung e.V., München, Bayern"),
                       ("exzellenz", "Technische Universität München, Muenchen, Bayern"),
                       ("uni", "Universität Bielefeld, Bielefeld, Nordrhein-Westfalen"),
                       ("haw", "Hochschule Reutlingen, Reutlingen, Baden-Württemberg")):
        r = run(lead(empf=empf, stelle=empf))
        werte[name] = teil(r, "team", "forschungsumfeld")["punkte"]
        assert "(Proxy)" in next(e["aussage"] for e in r["evidence"] if e["kriterium"] == "forschungsumfeld")
    assert werte["aussen"] > werte["exzellenz"] > werte["uni"] > werte["haw"] > 50


def test_excellence_list_follows_the_funding_phase():
    """Exzellenzstrategie: Konstanz nur bis 31.12.2026, Köln/Freiburg/Jena/Bochum/Dortmund/Frankfurt/Mainz ab 01.01.2027."""
    def klasse(empf, tag):
        r = run(lead(empf=empf, stelle=empf), tag)
        return next(e["aussage"] for e in r["evidence"] if e["kriterium"] == "forschungsumfeld")
    exz, uni = "(TU9-/Exzellenzuniversität)", "(Universität)"
    for empf, vorher, nachher in (("Universität Konstanz, Konstanz, Baden-Württemberg", exz, uni),
                                  ("Universität zu Köln, Köln, Nordrhein-Westfalen", uni, exz),
                                  ("Ruhr-Universität Bochum, Bochum, Nordrhein-Westfalen", uni, exz),
                                  ("Johann Wolfgang Goethe-Universität Frankfurt am Main, Frankfurt, Hessen", uni, exz),
                                  ("Universität Heidelberg, Heidelberg, Baden-Württemberg", exz, exz),   # behält den Titel
                                  ("Universität Bielefeld, Bielefeld, Nordrhein-Westfalen", uni, uni)):
        assert vorher in klasse(empf, date(2026, 11, 21)), empf
        assert nachher in klasse(empf, date(2027, 1, 1)), empf


def test_stipendium_sum_gives_minimum_team_size():
    def eg(summe, ende=date(2026, 5, 31)):
        return run(lead(fkz="03EGBY0003", programm="EXIST-Gründungsstipendium", summe=summe, start=date(2025, 6, 1), ende=ende))
    drei, zwei, eins = eg(135_000), eg(100_500), eg(50_000)
    assert "mind. 3 geförderte Personen" in next(e["aussage"] for e in drei["evidence"] if e["kriterium"] == "komplementaer")
    assert teil(drei, "team", "komplementaer")["punkte"] > teil(zwei, "team", "komplementaer")["punkte"] > 50
    assert not teil(eins, "team", "komplementaer")["belegt"]  # eine Person ist kein Beleg für "solo"
    # 135.000 EUR über 15 statt 12 Monate: weniger Personen nötig
    assert "mind. 2" in next(e["aussage"] for e in eg(120_000, ende=date(2026, 8, 31))["evidence"] if e["kriterium"] == "komplementaer")


@pytest.mark.parametrize("ende,punkte", [
    (date(2027, 2, 28), 100.0),   # endet in 3 Monaten: Gründungsfenster
    (date(2026, 7, 31), 100.0),   # endete vor 3 Monaten
    (date(2027, 8, 31), 85.0),    # in 9 Monaten
    (date(2028, 6, 30), 65.0),    # in 19 Monaten
    (date(2026, 1, 31), 60.0),    # vor 9 Monaten
    (date(2025, 6, 30), 30.0),    # vor 16 Monaten
])
def test_timing_from_funding_end(ende, punkte):
    r = run(lead(start=date(2024, 6, 1), ende=ende))
    assert teil(r, "marktpotenzial", "timing")["punkte"] == punkte


def test_long_running_and_long_ended_grants_in_why_now():
    lauf = run(lead(start=date(2026, 6, 1), ende=date(2028, 5, 31)))
    assert "EXIST-Forschungstransfer läuft bis 05/2028" in lauf["why_now"]
    alt = run(lead(start=date(2023, 6, 1), ende=date(2024, 12, 31)))
    assert "lief bis 12/2024 – Status prüfen" in alt["why_now"] and "endete" not in alt["why_now"]


def test_subject_proxies_software_hardware_medicine_and_non_tech():
    sw = run(lead(stelle="Technische Universität München - Fakultät für Informatik - Lehrstuhl für Software Engineering, München, Bayern"))
    hw = run(lead())
    med = run(lead(empf="Charité - Universitätsmedizin Berlin, Berlin, Berlin",
                   stelle="Charité - Universitätsmedizin Berlin - Klinik für Kardiologie, Berlin, Berlin"))
    kunst = run(lead(fkz="03EGHE0004", programm="EXIST-Gründungsstipendium", summe=60_000,
                     empf="Universität Kassel, Kassel, Hessen", stelle="Universität Kassel - Kunsthochschule, Visuelle Kommunikation, Kassel, Hessen"))
    assert teil(sw, "marktpotenzial", "skalierbarkeit")["punkte"] > teil(hw, "marktpotenzial", "skalierbarkeit")["punkte"]
    assert teil(med, "risiko", "regulatorik")["belegt"] and teil(med, "risiko", "regulatorik")["punkte"] > 50
    assert not teil(hw, "risiko", "regulatorik")["belegt"]  # kein Medizinbezug heißt nicht "unreguliert"
    assert teil(kunst, "marktpotenzial", "tech_tiefe")["punkte"] < 50


def test_self_description_keywords_do_not_create_proxies():
    """Schlagworte in einer Selbstbeschreibung sind Behauptungen: nur die Katalogseite speist die Fachgebiets-Proxies."""
    basis = {"lead_id": "t", "name_unternehmen": {"wert": "Quanten-Robotik", "quelle": "https://example.org"},
             "beschreibung_rohtext": {"wert": "Wir bauen Quantenbatterien und Laser-Roboter.", "quelle": "https://example.org"},
             "deutschland_beleg": {"wert": "Berlin", "quelle": "https://example.org"},
             "signals": [{"url": "https://example.org", "datum": "2026-09-01"}]}
    r = score_dossier(basis, CFG, TAG)
    assert not any(v["belegt"] for d in ("team", "marktpotenzial") for v in r["teilwerte"][d].values())


def test_proxies_count_half_for_confidence():
    r = run(lead())
    voll = sum(v["gewicht"] for d in ("team", "marktpotenzial", "risiko") for v in r["teilwerte"][d].values() if v["belegt"] and not v["proxy"])
    assert any(v["proxy"] for d in r["teilwerte"].values() for v in d.values())
    assert 0 < r["confidence"] < 0.4 and voll > 0  # dünne Katalog-Leads bleiben unter der Hypothesen-Schwelle
    assert r["investmenthypothese"].startswith("Datenlage zu dünn für eine Hypothese")
    assert "Wenn bis Förderende 01/2027 die Gründung gelingt" in r["investmenthypothese"]


# --- 4. Texte aus belegten Katalog-Fakten statt Platzhalter --------------------------------------------------------
def test_placeholder_description_is_replaced_by_catalogue_facts():
    r = run(lead())
    assert "Projekt im Programm" not in r["value_proposition"]
    assert r["value_proposition"].startswith("„QuantSense“ – EXIST-Forschungstransfer-Vorhaben aus Lehrstuhl für Physik der Quantensensorik")
    assert "1,0 Mio. EUR" in r["produktbeschreibung"] and "06/2025–01/2027" in r["produktbeschreibung"]
    assert "noch nicht belegt" in r["produktbeschreibung"]
    lang = run(lead(stelle="Technische Universität München - " + "Lehrstuhl für sehr lange Namen " * 20 + ", Garching, Bayern"))
    assert len(lang["value_proposition"]) <= 200 and len(lang["produktbeschreibung"]) <= 300 and len(lang["investmenthypothese"]) <= 400


def test_renamed_project_placeholder_is_replaced_too():
    r = run(lead(description="„JoulyAI“ (ehemals „Minmo“) – Projekt im Programm EXIST-Forschungstransfer."))
    assert "Projekt im Programm" not in r["value_proposition"]


def test_real_description_is_kept_verbatim():
    r = run(lead(description="Chipbasierte ESR-Sensorik für die Qualitätskontrolle. Zweiter Satz. Dritter Satz."))
    assert r["value_proposition"] == "Chipbasierte ESR-Sensorik für die Qualitätskontrolle."


# --- 2. Altes Gründungsjahr aus Pressetext (kiutra) ----------------------------------------------------------------
def kiutra_like(**extra):
    q = "https://kiutra.example/impressum"
    d = {"lead_id": "k", "name_unternehmen": {"wert": "K GmbH", "quelle": q},
         "beschreibung_rohtext": {"wert": "Kryogene Kühlsysteme.", "quelle": q}, "deutschland_beleg": {"wert": "München", "quelle": q},
         "gruendungsjahr_hinweis": {"wert": 2018, "quelle": IDW},
         "signals": [{"url": "https://web.archive.org/web/20190304/http://k.example", "datum": "2019-03-04"},
                     {"url": IDW, "datum": "2022-07-01"}]}
    d.update(extra)
    return d


def test_old_press_year_confirmed_by_legal_form_or_database_is_too_late():
    gmbh = score_dossier(kiutra_like(rechtsform={"wert": "GmbH", "quelle": "https://kiutra.example/impressum"}), CFG, TAG)
    assert gmbh["stage"] == "zu_spaet" and gmbh["gesamt_score"] <= 20
    assert "gegründet 2018 laut Pressetext, bestätigt durch Rechtsform GmbH" in gmbh["ausschluss_grund"]
    db = score_dossier(kiutra_like(in_databases=True), CFG, TAG)
    assert db["stage"] == "zu_spaet" and "Datenbankeintrag" in db["ausschluss_grund"]


def test_old_press_year_without_confirmation_is_an_open_point_not_an_exclusion():
    r = score_dossier(kiutra_like(), CFG, TAG)
    assert r["stage"] == "pre_seed" and r["ausschluss_grund"] == ""
    assert any("nicht durch Rechtsform oder Datenbankeintrag bestätigt" in p for p in r["offene_punkte"])


def test_namesake_guard_still_wins():
    """Pressetext-Jahr mehr als 24 Monate vor dem ersten Signal = Fremdbezug: kein Ausschluss, auch mit GmbH."""
    r = score_dossier(kiutra_like(gruendungsjahr_hinweis={"wert": 2013, "quelle": IDW},
                                  rechtsform={"wert": "GmbH", "quelle": "https://kiutra.example/impressum"},
                                  signals=[{"url": "https://exist.example/p", "datum": "2025-10-01"}]), CFG, TAG)
    assert r["stage"] == "pre_seed" and r["ausschluss_grund"] == ""
    assert any(p.startswith("Gründungsjahr 2013 aus Pressetext liegt mehr als 24 Monate") for p in r["offene_punkte"])


def test_young_press_year_is_still_only_a_proxy():
    r = score_dossier(kiutra_like(gruendungsjahr_hinweis={"wert": 2025, "quelle": IDW},
                                  rechtsform={"wert": "GmbH", "quelle": "https://kiutra.example/impressum"},
                                  signals=[{"url": IDW, "datum": "2025-09-01"}]), CFG, TAG)
    assert r["stage"] == "pre_seed" and r["ausschluss_grund"] == ""


def test_old_database_profile_consistent_with_own_signals_is_too_late():
    alt = score_dossier(kiutra_like(gruendungsjahr_hinweis=None, in_databases=True, first_db_date="2019-03-11"), CFG, TAG)
    assert alt["stage"] == "zu_spaet" and "Datenbankprofil seit 03/2019" in alt["ausschluss_grund"]
    # Profil 2019, eigene Signale erst 2025: Namensvetter, kein Ausschluss
    fremd = score_dossier(kiutra_like(gruendungsjahr_hinweis=None, in_databases=True, first_db_date="2019-03-11",
                                      signals=[{"url": "https://exist.example/p", "datum": "2025-10-01"}]), CFG, TAG)
    assert fremd["stage"] != "zu_spaet"
    # junges Profil: kein Ausschluss
    jung = score_dossier(kiutra_like(gruendungsjahr_hinweis=None, in_databases=True, first_db_date="2025-01-11"), CFG, TAG)
    assert jung["stage"] != "zu_spaet"


def test_kiutra_example_is_too_late():
    from scoring.sources import load_dossiers
    rows = {r["lead_id"]: r for r in score_all(load_dossiers(ROOT / "examples/context/real_dossiers.json", CFG), CFG, TAG)}
    assert rows["kiutra"]["stage"] == "zu_spaet" and rows["kiutra"]["gesamt_score"] == 20
    assert all(rows[x]["stage"] != "zu_spaet" for x in ("siderogain", "spinmagic", "hochquant"))


# --- 3. Noise-Filter --------------------------------------------------------------------------------------------
def test_service_project_title_is_noise_without_website():
    assert run(lead(thema="Müller Unternehmensberatung", name="Müller Unternehmensberatung"))["noise_class"] == "beratung"
    assert run(lead(thema="Pixel Werbeagentur", name="Pixel Werbeagentur"))["noise_class"] == "agentur"
    for titel in ("QuantSense", "DieMarketingIdee", "Beratungsroboter", "AgentFlow"):  # Wortteil am Anfang/ohne Dienstleistung
        assert run(lead(thema=titel, name=titel))["noise_class"] == "vc_potenzial", titel


def website(text, quelle="https://firma.example/"):
    return Evidence(source="Unternehmenswebsite", url=quelle, finding=text, field="website_text",
                    retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc))


def test_website_text_from_context_reaches_noise_filter():
    agentur = lead(evidence=[website("Unsere Leistungen: Webdesign, SEO und Beratung. Referenzen. Wir sind Ihre Digitalagentur.")])
    assert to_dossier(agentur, CFG)["website_text"]["quelle"] == "https://firma.example/"
    r = run(agentur)
    assert r["noise_class"] == "agentur" and r["gesamt_score"] <= 20
    beratung = lead(evidence=[website("Unternehmensberatung und Consulting für den Mittelstand. Beratung zu Strategie.")])
    assert run(beratung)["noise_class"] == "beratung"
    modell = lead(evidence=[website("Agentur Beratung Webdesign", "https://firma.example/x").model_copy(update={"source": "Ollama-Zitat aus Website"})])
    assert to_dossier(modell, CFG)["website_text"] is None


@pytest.mark.parametrize("text", [
    "Wir sind keine Agentur und bieten keine Beratung, sondern ein eigenes Produkt.",
    "Unsere Leistungen: Quantensensor-Chip mit Patent. Referenzen: Pilot mit BASF. Technologie aus der Forschung der TUM.",
    "Leistungen · Referenzen · Team · Karriere",
    "Spin-off der Universität Stuttgart: Sensor-Hardware, Prototyp im Labor, Beratung zur Integration für Kunden.",
])
def test_deep_tech_websites_are_not_noise(text):
    assert run(lead(evidence=[website(text)]))["noise_class"] == "vc_potenzial"


def test_no_noise_false_positives_on_catalogue_examples():
    from scoring.sources import load_dossiers
    for f in ("examples/sourcing/sample_dossiers.json", "examples/context/real_dossiers.json"):
        rows = score_all(load_dossiers(ROOT / f, CFG), CFG, TAG)
        assert {r["noise_class"] for r in rows} == {"vc_potenzial"}, f


def test_every_evidence_without_url_is_marked_neutral_or_sourcing():
    """QA M2: Jede Evidence hat eine URL oder sagt ausdrücklich "neutral" bzw. "laut Sourcing"."""
    from scoring.sources import load_dossiers
    rows = [run(lead()), score_dossier({"lead_id": "s", "name_unternehmen": {"wert": "S", "quelle": "https://s.example"},
                                        "beschreibung_rohtext": {"wert": "S.", "quelle": "https://s.example"},
                                        "deutschland_beleg": {"wert": "DE", "quelle": "https://s.example"}, "noise_class": "bereits_finanziert",
                                        "signals": [{"url": "https://s.example", "datum": "2026-01-01"}]}, CFG, TAG)]
    rows += score_all(load_dossiers(ROOT / "examples/sourcing/sample_dossiers.json", CFG), CFG, TAG)
    rows += score_all(load_dossiers(ROOT / "scoring/testleads/dummy_leads.json", CFG), CFG, TAG)
    for r in rows:
        for e in r["evidence"]:
            assert e["url"] or "neutral" in e["aussage"] or "laut Sourcing" in e["aussage"], (r["lead_id"], e)
    assert any(e["aussage"] == "pre_gruendung: keine Rechtsform belegt – keine Daten, neutral gesetzt" for e in rows[0]["evidence"])


# --- 5. Determinismus und Streuung ---------------------------------------------------------------------------------
def test_deterministic_and_spread_on_sample():
    from scoring.sources import load_dossiers
    dossiers = load_dossiers(ROOT / "examples/sourcing/sample_dossiers.json", CFG)
    a = score_all(copy.deepcopy(dossiers), CFG, TAG)
    b = score_all(copy.deepcopy(dossiers), CFG, TAG)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    scores = [r["gesamt_score"] for r in a if r["gesamt_score"] is not None]
    # acht Forschungstransfer-Leads, vor T2 51,8–53,7 mit Gleichständen; timing wiegt seit der Kalibrierung nur noch 0,05
    assert len(set(scores)) >= 6 and max(scores) - min(scores) >= 2.5
    assert all("Projekt im Programm" not in r["value_proposition"] for r in a)


# --- Kalibrierungsrunde: Geschäftsführung, Timing gegründeter Teams, seed nur mit Bestätigung ---------------------------
IMP = "https://firma.example/impressum"


def ev(field, url, finding="x", source="Impressum"):
    return Evidence(source=source, url=url, finding=finding, field=field, retrieved_at=datetime(2026, 11, 20, tzinfo=timezone.utc))


def gegruendet(**changes):
    return lead(legal_form="GmbH", imprint_url=IMP, evidence=[ev("legal_form", IMP, "Firma GmbH"),
                                                              ev("managing_directors", IMP, "Geschäftsführer: …")] + changes.pop("evidence", []),
                **changes)


def test_managing_directors_become_team_with_imprint_source():
    from models import FounderProfile
    x = gegruendet(managing_directors=["Dr. Anna Beispiel", "Ben Muster", "Commercial Register", "VAT ID", "Rector Kerstin Krieglstein"],
                   founder_profiles=[FounderProfile(name="Ben Muster", openalex_url="https://openalex.org/A1", works_in_field=12,
                                                    source_url="https://openalex.org/A1")])
    team = to_dossier(x, CFG)["team"]
    assert [(t["name"], t["rolle"]) for t in team] == [("Ben Muster", "Gründer"), ("Anna Beispiel", "Geschäftsführung")]
    assert team[1]["quelle"] == IMP and team[1]["herkunft"] == "impressum"
    r = run(x)
    assert r["name_gruender"] == "Anna Beispiel;Ben Muster"  # Rollen "Geschäftsführung" und "Gründer" zählen beide
    assert teil(r, "team", "forscher_match")["belegt"]      # Papers aus dem Profil kommen an
    # ohne Impressum-Beleg keine Übernahme
    assert all(t.get("herkunft") != "impressum" for t in to_dossier(lead(managing_directors=["Anna Beispiel"]), CFG)["team"])


def test_single_imprint_director_is_not_a_solo_founder():
    from models import FounderProfile
    r = run(gegruendet(managing_directors=["Anna Beispiel"]))
    assert teil(r, "team", "komplementaer")["punkte"] > 50  # Forschungsteam-Proxy statt "solo" (20)
    assert r["noise_class"] == "vc_potenzial"
    # context liefert dieselbe Person als Profil mit Rolle "Geschäftsführung (Impressum)": einmal im Team, nicht solo
    prof = FounderProfile(name="Anna Beispiel", role="Geschäftsführung (Impressum)", source_url="https://openalex.org/A2",
                          openalex_url="https://openalex.org/A2", works_in_field=4)
    x = gegruendet(managing_directors=["Anna Beispiel"], founder_profiles=[prof])
    team = to_dossier(x, CFG)["team"]
    assert len(team) == 1 and team[0]["herkunft"] == "impressum" and team[0]["papers_im_feld"] == 4
    assert teil(run(x), "team", "komplementaer")["punkte"] > 50
    muell = gegruendet(founder_profiles=[FounderProfile(name="Commercial Register", role="Geschäftsführung (Impressum)")])
    assert to_dossier(muell, CFG)["team"] == []


def test_timing_rewards_founded_teams_at_funding_end():
    ohne = run(lead(start=date(2024, 6, 1), ende=date(2026, 2, 28)))                      # endete vor 8 Monaten
    mit = run(gegruendet(start=date(2024, 6, 1), ende=date(2026, 2, 28)))
    assert teil(ohne, "marktpotenzial", "timing")["punkte"] == 60.0
    assert teil(mit, "marktpotenzial", "timing")["punkte"] == 90.0
    assert "Anschlussfinanzierung" in next(e["aussage"] for e in mit["evidence"] if e["kriterium"] == "timing")
    lang_her = run(gegruendet(start=date(2023, 6, 1), ende=date(2025, 5, 31)))           # 17 Monate her: alte Stufe
    assert teil(lang_her, "marktpotenzial", "timing")["punkte"] == 30.0


def test_seed_needs_independent_maturity_evidence():
    """M-Shunt: eine Website-Textstelle "erste Kunden" + GmbH ergab seed mit niedrigem Risiko."""
    web = "https://firma.example/products"
    einzeln = gegruendet(product_stage="erste_kunden", evidence=[ev("product_stage", web, "pricing", "Unternehmenswebsite"),
                                                                 ev("product_stage", "https://firma.example/", "kits", "Unternehmenswebsite")])
    r = run(einzeln)
    assert r["stage"] == "pre_seed" and "nur aus einer Quelle" in next(e["aussage"] for e in r["evidence"] if e["dimension"] == "stage")
    assert teil(r, "risiko", "tech_reife")["proxy"] and teil(r, "risiko", "tech_reife")["punkte"] > 15
    zwei = gegruendet(product_stage="erste_kunden", evidence=[ev("product_stage", web, "pricing", "Unternehmenswebsite"),
                                                              ev("product_stage", "https://idw-online.de/de/news1", "Kunden", "idw")])
    assert run(zwei)["stage"] == "seed"
    # Modellzitate zählen nicht als zweite Quelle
    zitat = gegruendet(product_stage="erste_kunden", evidence=[ev("product_stage", web, "pricing", "Unternehmenswebsite"),
                                                               ev("product_stage", "https://idw-online.de/de/news1", "K", "Ollama-Zitat aus idw")])
    assert run(zitat)["stage"] == "pre_seed"
    # handgepflegtes Dossier ohne reifegrad_quellen: wie bisher
    q = {"quelle": "https://example.org"}
    d = {"lead_id": "h", "name_unternehmen": {"wert": "H", **q}, "beschreibung_rohtext": {"wert": "H.", **q},
         "deutschland_beleg": {"wert": "DE", **q}, "signals": [{"url": "https://example.org", "datum": "2026-01-01"}],
         "rechtsform": {"wert": "GmbH", **q}, "reifegrad": {"wert": "pilot", **q}}
    assert score_dossier(d, CFG, TAG)["stage"] == "seed"


def test_total_works_count_as_weak_researcher_proxy():
    from models import FounderProfile
    def mit(works, mc):
        prof = FounderProfile(name="Anna Beispiel", role="Geschäftsführung (Impressum)", source_url="https://openalex.org/A3",
                              openalex_url="https://openalex.org/A3", works_total=works, match_confidence=mc)
        return teil(run(gegruendet(founder_profiles=[prof])), "team", "forscher_match")
    viel, wenig, unsicher = mit(40, 0.9), mit(3, 0.9), mit(40, 0.3)
    assert viel["proxy"] and viel["punkte"] > wenig["punkte"] > 50
    assert not unsicher["belegt"]  # unsichere Zuordnung bleibt neutral


def test_name_dedup_keeps_distinct_people():
    from models import FounderProfile
    profile = [FounderProfile(name="Person %02d" % i, source_url="https://openalex.org/A%d" % i) for i in (1, 2, 3)]
    profile.append(FounderProfile(name="person 01", source_url="https://openalex.org/A9"))  # gleiche Person, andere Schreibweise
    assert [t["name"] for t in to_dossier(lead(founder_profiles=profile), CFG)["team"]] == ["Person 01", "Person 02", "Person 03"]


# --- Final Gate M1–M3, m3 --------------------------------------------------------------------------------------------
def partner_lead(*partner):
    from models import Partner
    return gegruendet(partners=[Partner(name=n, kind=k, quote=q, url="https://firma.example/") for n, k, q in partner])


def test_funders_and_generic_phrases_are_not_traction():
    """M1: BotFellows "Global Partners", SpinMagIC Bundesministerium als design_partner, SIMBA zerschnittener Institutsname."""
    for p in [("Global Partners", "kunde", "Trusted by Global Partners")],                                   \
             [("Federal Ministry for Economic Affairs", "design_partner", "The European Union, together with the Federal "
               "Ministry for Economic Affairs and Climate Protection"),
              ("Climate Protection", "design_partner", "together with the Federal Ministry for Economic Affairs and Climate Protection")], \
             [("EXIST", "design_partner", "gefördert durch EXIST")], [("Our Customers", "kunde", "Our Customers")]:
        r = run(partner_lead(*p))
        assert not teil(r, "marktpotenzial", "traktion")["belegt"], p
        assert "belegte Partner" not in r["investmenthypothese"] and "belegter Partner" not in r["investmenthypothese"]
    zitat = "In Zusammenarbeit mit dem Fraunhofer-Institut für Software- und Systemtechnik ISST und der TU Dortmund"
    r = run(partner_lead(("Fraunhofer-Institut für Software", "forschungspartner", zitat),
                         ("Systemtechnik ISST", "design_partner", zitat)))
    e = next(e for e in r["evidence"] if e["kriterium"] == "traktion")
    assert e["aussage"] == "1 belegter Partner; stärkster: Fraunhofer-Institut für Software- und Systemtechnik ISST (forschungspartner)"
    # Firma mit Rechtsform zählt voll, ein unbekannter Name nur als Proxy
    voll = teil(run(partner_lead(("Freiberger Compound Materials GmbH", "pilot", "Pilotanlage mit Freiberger Compound Materials GmbH"))),
                "marktpotenzial", "traktion")
    proxy = teil(run(partner_lead(("Acme Robotics", "pilot", "Pilot mit Acme Robotics"))), "marktpotenzial", "traktion")
    assert voll["punkte"] == 85.0 and not voll["proxy"] and proxy["proxy"] and 50 < proxy["punkte"] < 85
    zitat_rf = teil(run(partner_lead(("Freiberger Compound Materials", "pilot",
                                      "Gemeinsam mit dem Halbleiterhersteller Freiberger Compound Materials (FCM) GmbH übertrug"))),
                    "marktpotenzial", "traktion")
    assert zitat_rf["punkte"] == 85.0 and not zitat_rf["proxy"]


def test_value_proposition_from_website_text():
    """M2: Website-Text liegt vor -> extraktive VP statt Katalog-Platzhalter; Navigation, CTA, Förderhinweis raus."""
    text = ("Pulse of Production | Fertigung verstehen\nKontakt\nWerkzeugprobleme erkennen, bevor sie Stillstand verursachen.\n"
            "Werkzeug-\nprobleme erkennen, bevor sie Stillstand verursachen.\nEchtzeitüberwachung Ihrer Umform- und Stanzwerkzeuge – "
            "ohne Eingriff in die Maschinensteuerung.\nDemo anfragen →\nGefördert durch das Bundesministerium für Wirtschaft im Programm EXIST.")
    r = run(lead(evidence=[website(text)]))
    assert r["value_proposition"] == ("Werkzeugprobleme erkennen, bevor sie Stillstand verursachen. Echtzeitüberwachung Ihrer Umform- "
                                      "und Stanzwerkzeuge – ohne Eingriff in die Maschinensteuerung.")
    assert len(r["value_proposition"]) <= 200 and "EXIST" not in r["produktbeschreibung"] and "Kontakt" not in r["produktbeschreibung"]
    # Baukasten-Seite mit Lorem ipsum: Katalog-Fakten statt Blindtext
    lorem = run(lead(evidence=[website("Lorem ipsum dolor sit amet, consectetur adipiscing elit.\nNulla euismod condimentum felis vitae efficitur.")]))
    assert "Lorem" not in lorem["value_proposition"] and "Nulla" not in lorem["value_proposition"]
    # echte Beschreibung hat Vorrang vor der Website
    assert run(lead(description="Chip-ESR-Sensor für Lebensmittel.", evidence=[website(text)]))["value_proposition"] == "Chip-ESR-Sensor für Lebensmittel."


def test_long_institution_name_is_not_cut_mid_word():
    stelle = ("Rheinisch-Westfälische Technische Hochschule Aachen - Lehrstuhl für Heterogene Katalyse und Technische Chemie, "
              "Aachen, Nordrhein-Westfalen")
    r = run(lead(stelle=stelle, empf="Rheinisch-Westfälische Technische Hochschule Aachen, Aachen, Nordrhein-Westfalen"))
    assert r["value_proposition"].startswith("„QuantSense“ – EXIST-Forschungstransfer-Vorhaben aus Lehrstuhl für Heterogene Katalyse und Technische Chemie;")
    assert "Technische…" not in r["value_proposition"] + r["produktbeschreibung"]


def db_ev(url, finding="x", source="Wayback CDX"):
    return ev("in_databases", url, finding, source)


def test_why_now_names_the_kind_of_database_check():
    """M3: Wayback prüft nur archivierte Profil-Slugs; nur eine echte Suche darf "nicht gefunden" sagen."""
    wb = run(lead(in_databases=False, evidence=[db_ev("https://web.archive.org/cdx/search/cdx?url=dealroom.co/companies/x")]))
    assert "kein archiviertes Crunchbase-/Dealroom-Profil (Wayback)" in wb["why_now"] and "nicht gefunden" not in wb["why_now"]
    such = run(lead(in_databases=False, evidence=[db_ev("https://web.archive.org/cdx/x"),
                                                  db_ev("https://search.brave.com/search?q=x", "kein Profil gefunden", "Datenbanksuche (Brave)")]))
    assert "nicht gefunden (Datenbanksuche)" in such["why_now"]
    treffer = run(lead(in_databases=True, evidence=[db_ev("https://app.dealroom.co/companies/quantsense", "Profil", "Datenbanksuche (Brave)")]))
    assert "bereits mit Datenbankprofil gelistet (app.dealroom.co)" in treffer["why_now"]
    assert treffer["earliness_delta_monate"] is None  # Profil ohne Datum: kein "noch nicht gelistet bis heute"
    assert any("Earliness nicht berechenbar" in p for p in treffer["offene_punkte"])


def test_team_texts_agree_and_milestone_needs_customers():
    """m3: name_gruender gesetzt -> komplementaer-Text nennt die Person; erste_kunden aus einer Quelle -> kein 'wiederholbarer Vertrieb'."""
    r = run(gegruendet(managing_directors=["Anna Beispiel"]))
    e = next(e for e in r["evidence"] if e["kriterium"] == "komplementaer")
    assert r["name_gruender"] == "Anna Beispiel" and e["aussage"].startswith("Anna Beispiel (Geschäftsführung), Teamgröße offen")
    assert "nicht namentlich" not in e["aussage"]
    einzeln = gegruendet(product_stage="erste_kunden", evidence=[ev("product_stage", "https://firma.example/p", "pricing", "Unternehmenswebsite")])
    h = run(einzeln)["investmenthypothese"]
    assert "wiederholbarer Vertrieb" not in h
    assert "1 belegter Partner" in next(e["aussage"] for e in run(partner_lead(("Beispiel GmbH", "kunde", "Kunde Beispiel GmbH")))["evidence"]
                                        if e["kriterium"] == "traktion")


# --- Loop Runde 1 (Coder B): Team-Zusammensetzung, n2, n1 --------------------------------------------------------------
def fp(name, role, background=None, url=None, **kw):
    from models import FounderProfile
    return FounderProfile(name=name, role=role, background=background,
                          source_url=url or "https://www.linkedin.com/in/%s/" % name.lower().replace(" ", "-"), **kw)


def komp(x):
    r = run(x)
    return r, teil(r, "team", "komplementaer"), next(e for e in r["evidence"] if e["kriterium"] == "komplementaer")


def test_linkedin_founder_and_imprint_director_merge_without_duplicate():
    x = gegruendet(managing_directors=["Anna Beispiel", "Ben Muster"],
                   founder_profiles=[fp("Anna Beispiel", "Geschäftsführung (Impressum); CTO & Co-Founder (LinkedIn)", "tech")])
    team = to_dossier(x, CFG)["team"]
    assert [t["name"] for t in team] == ["Anna Beispiel", "Ben Muster"]
    assert team[0]["herkuenfte"] == ["impressum", "linkedin"] and team[0]["gruender"] is True
    r, t, e = komp(x)
    assert e["aussage"].startswith("2 Personen in der Geschäftsführung, Profil-Mix unbekannt: "
                                   "Anna Beispiel (Geschäftsführung / CTO & Co-Founder, Tech), Ben Muster (Geschäftsführung)")
    assert t["punkte"] == 60.0  # Mix unbekannt bleibt 0,6, Ben ohne Hintergrund ist kein "ohne Business"


def test_business_cofounder_is_a_strength():
    x = gegruendet(founder_profiles=[fp("Eva Kauf", "CEO & Co-Founder (LinkedIn)", "business"),
                                     fp("Tom Technik", "CTO & Co-Founder (LinkedIn)", "tech")])
    r, t, e = komp(x)
    assert t["punkte"] == 100.0 and not t["proxy"]
    assert "Business-Profil: Eva Kauf" in e["aussage"] and e["url"] == "https://www.linkedin.com/in/eva-kauf/"
    assert "Technik und Business" in r["investmenthypothese"]
    assert not any("Business-Profil im Team nicht belegt" in p for p in r["offene_punkte"])


def test_without_business_only_when_all_founders_are_proven_tech():
    alle_tech = gegruendet(founder_profiles=[fp("A Eins", "CTO (LinkedIn)", "tech"), fp("B Zwei", "Co-Founder (LinkedIn)", "tech")])
    r, t, e = komp(alle_tech)
    assert t["punkte"] == 50.0 and "kein Business-Profil" in e["aussage"]
    assert "Business-Profil im Team nicht belegt – prüfen" in r["offene_punkte"]
    halb = gegruendet(founder_profiles=[fp("A Eins", "CTO (LinkedIn)", "tech"), fp("B Zwei", "CEO (LinkedIn)")])  # CEO allein: offen
    r, t, _ = komp(halb)
    assert t["punkte"] == 60.0 and not any("Business-Profil im Team" in p for p in r["offene_punkte"])


def test_team_members_count_for_mix_not_for_n():
    x = gegruendet(founder_profiles=[fp("A Eins", "CTO & Co-Founder (LinkedIn)", "tech"), fp("B Zwei", "Co-Founder (Presse)", "tech",
                                                                                            url="https://idw-online.de/de/news9"),
                                     fp("C Drei", "Teammitglied (LinkedIn)", "business")])
    r, t, e = komp(x)
    assert e["aussage"].startswith("2 Gründer mit Technik und Business") and "Business-Profil: C Drei" in e["aussage"]
    assert t["punkte"] == 100.0 and r["name_gruender"] == "A Eins;B Zwei"  # Teammitglied nicht in name_gruender
    nur_mitglieder = gegruendet(founder_profiles=[fp("C Drei", "Teammitglied (LinkedIn)", "business")])
    assert run(nur_mitglieder)["name_gruender"] == ""
    nur_mitglied = gegruendet(founder_profiles=[fp("A Eins", "Geschäftsführung (Impressum)", url=IMP),
                                                fp("C Drei", "Teammitglied (LinkedIn)", "business")])
    _, t, e = komp(nur_mitglied)
    assert t["proxy"] and e["aussage"].startswith("A Eins (Geschäftsführung), Teamgröße offen")  # n = 1, aber kein "solo"


def test_single_person_is_solo_only_when_a_source_says_so():
    for role in ("Gründer (Presse)", "CEO (LinkedIn)", "Geschäftsführung (Impressum)", None):  # None: OpenAlex-Profil aus context
        _, t, _ = komp(gegruendet(founder_profiles=[fp("A Eins", role, "tech")]))
        assert t["punkte"] > 50, role
    _, t, e = komp(gegruendet(founder_profiles=[fp("A Eins", "Alleingründer (Presse)", "tech")]))
    assert t["punkte"] == 20.0 and e["aussage"] == "Ein Gründer belegt: A Eins"


def test_database_hit_needs_a_profile_url_and_conflicts_are_flagged():
    """n2 HydroPURE: Wayback-Slug gefunden, Brave-Datenbanksuche ohne Profil -> keine Such-URL als Fundstelle, Konflikt offen."""
    wb = "https://web.archive.org/web/20241001082459/https://www.crunchbase.com/organization/quantsense"
    brave = "https://search.brave.com/search?q=%22QuantSense%22+site%3Adealroom.co"
    x = lead(in_databases=True, first_db_date=date(2024, 10, 1), database_urls=[wb],
             evidence=[db_ev(wb, "Crunchbase-Profil im Webarchiv"), db_ev(brave, "kein Profil", "Datenbanksuche (Brave)")])
    d = to_dossier(x, CFG)
    assert d["in_databases_quelle"] == wb and d["in_databases_konflikt"] is True
    r = run(x)
    assert "search.brave.com" not in r["why_now"] and "Namensvetter prüfen" in r["why_now"]
    assert any("Namensvetter prüfen" in p for p in r["offene_punkte"])
    treffer = lead(in_databases=True, database_urls=["https://app.dealroom.co/companies/quantsense"],
                   evidence=[db_ev("https://app.dealroom.co/companies/quantsense", "Profil", "Datenbanksuche (Brave)")])
    d = to_dossier(treffer, CFG)
    assert d["in_databases_quelle"] == "https://app.dealroom.co/companies/quantsense" and d["in_databases_konflikt"] is False
    assert "(app.dealroom.co)" in run(treffer)["why_now"]


@pytest.mark.parametrize("text,erwartet", [
    ("iNSyT solutions – Observing without Disturbing Skip to content\nHome\nApplications\nApplications – Coatings & thin Layers\n"
     "Contact\nHome\nApplications\nApplications – Coatings & thin Layers\nContact\nNanoscale dynamics, made visible\n"
     "Get insights in dynamics of objects down to the nanoscale in real time – and in their native environment.\nLearn More\n"
     "Our real-time, non-invasive technology brings unseen processes to light — faster, simpler, and more precise than ever before",
     "Our real-time, non-invasive technology brings unseen processes to light"),
    ("metubiq - Measure Everywhere\nTechnology\nMastering vibration for uncompromised accuracy.\n"
     "From understanding vibration effects to dynamic signal correction and seamless machine integration—explore our core technology.\n"
     "Vibration CorrectionReliable measurement in dynamic environments Influence of VibrationsHow environmental vibrations corrupt data\n"
     "Laboratory Precision on the Shop Floor\nGain early access to our latest measurement technology and work directly with our team.",
     "Gain early access to our latest measurement technology"),
    ("SpinMagIC - Home\nHome About News Contacts\nWe bring EPR to people\nFree radicals are a critical indicator of material degradation.\n"
     "Our cutting-edge quantum sensor enables precise, real-time monitoring of free radicals throughout your processes.",
     "Our cutting-edge quantum sensor enables precise, real-time monitoring"),
])
def test_website_vp_skips_menus_and_calls_to_action(text, erwartet):
    vp = run(lead(evidence=[website(text)]))["value_proposition"]
    assert vp.startswith(erwartet), vp
    assert not re.search(r"(?i)applications –|explore|skip to|learn more", vp)


def test_openalex_fallback_tech_is_no_proof_of_missing_business():
    """Prüfung Runde 1, MAJOR 1: tech nur aus "ab 5 Arbeiten" (OpenAlex) -> Mix unbekannt (0,6), kein "ohne Business"."""
    oa = [ev("founder_profiles", "https://openalex.org/A1", "Alexander Reder: background tech aus OpenAlex (40 Arbeiten)", "OpenAlex"),
          ev("founder_profiles", "https://openalex.org/A2", "Chris Hentschel: background tech aus OpenAlex (12 Arbeiten)", "OpenAlex")]
    profile = [fp("Alexander Reder", "Geschäftsführung (Impressum)", "tech", url=IMP), fp("Chris Hentschel", "Geschäftsführung (Impressum)", "tech", url=IMP)]
    r, t, e = komp(gegruendet(founder_profiles=profile, evidence=oa))
    assert t["punkte"] == 60.0 and "Profil-Mix unbekannt" in e["aussage"]
    assert not any("Business-Profil im Team nicht belegt" in p for p in r["offene_punkte"])
    # einer ausdrücklich (Rolle "CTO"), einer nur OpenAlex: weiterhin offen
    gemischt = [fp("Alexander Reder", "CTO (LinkedIn)", "tech"), fp("Chris Hentschel", "Geschäftsführung (Impressum)", "tech", url=IMP)]
    assert komp(gegruendet(founder_profiles=gemischt, evidence=oa[1:]))[1]["punkte"] == 60.0
    # beide ausdrücklich tech: "ohne Business" wie bisher
    explizit = [fp("Alexander Reder", "CTO (LinkedIn)", "tech"), fp("Chris Hentschel", "Co-Founder & Head of Engineering (LinkedIn)", "tech")]
    assert komp(gegruendet(founder_profiles=explizit))[1]["punkte"] == 50.0
    # tech aus OpenAlex + ausdrücklicher Business-Co-Founder: Mix belegt
    mix = [fp("Alexander Reder", "Geschäftsführung (Impressum)", "tech", url=IMP), fp("Eva Kauf", "CFO & Co-Founder (LinkedIn)", "business")]
    assert komp(gegruendet(founder_profiles=mix, evidence=oa[:1]))[1]["punkte"] == 100.0
