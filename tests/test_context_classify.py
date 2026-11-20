"""Offline tests for context.classify: rules, conflict handling and the quote-checked model layer."""
import json
from datetime import date
from pathlib import Path

import pytest

from context.cache import Cache, NoCache
from context.classify import MODEL_FIELDS, build_schema, classify_texts, parse_money, prompt_text
from models import SourceSignal

FIXTURES = Path(__file__).parent / "fixtures" / "context"
URL = "https://example-startup.de/produkt"


def sig(text, url=URL, type="website", source="Unternehmenswebsite", day=None):
    return SourceSignal(source=source, type=type, url=url, date=day, evidence=text)


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def run(*signals, model=None, ask=None, name="Beispiel Energie GmbH", cache=None):
    return classify_texts(name, list(signals), model=model, cache=cache or NoCache(), ask=ask)


def findings(result, field):
    return [e.finding for e in result.evidence if e.field == field]


# ----------------------------------------------------------------- IP

@pytest.mark.parametrize("line, status", [
    ("Unser Verfahren ist zum Patent angemeldet.", "patent_angemeldet"),
    ("Die Patentanmeldung wurde 2025 eingereicht.", "patent_angemeldet"),
    ("Our core technology is patent pending.", "patent_angemeldet"),
    ("We have filed two patent applications in Europe.", "patent_angemeldet"),
    ("Das Patent wurde 2024 erteilt.", "patent_erteilt"),
    ("Patentierte Technologie für die Prüfung von Schweißnähten.", "patent_erteilt"),
    ("Our patented sensor array measures vibration.", "patent_erteilt"),
    ("The patent was granted by the EPO.", "patent_erteilt"),
    ("Wir halten kein Patent, unser Vorsprung liegt im Datensatz.", "keine"),
    ("The approach is not patented.", "keine"),
])
def test_ip_rules_german_and_english(line, status):
    result = run(sig(f"Über uns\n{line}\nKontakt", day=date(2026, 1, 5)))
    assert result.fields["ip_status"] == status
    assert findings(result, "ip_status") == [line]
    evidence = next(e for e in result.evidence if e.field == "ip_status")
    assert str(evidence.url) == URL and evidence.source_date == date(2026, 1, 5)
    if status == "keine":
        assert "patents" not in result.fields
    else:
        (patent,) = result.fields["patents"]
        assert patent.status == status and patent.quote == line and str(patent.url) == URL


def test_granted_patent_outranks_pending_one():
    result = run(sig("Ein Patent wurde erteilt.\nZwei weitere Patente sind angemeldet."))
    assert result.fields["ip_status"] == "patent_erteilt"
    assert [p.status for p in result.fields["patents"]] == ["patent_erteilt", "patent_angemeldet"]


# ----------------------------------------------------------------- partners

@pytest.mark.parametrize("line, expected", [
    ("Pilotkunde ist die Deutsche Bahn.", [("Deutsche Bahn", "pilot")]),
    ("Pilotprojekt mit der Charité Berlin und Siemens Healthineers läuft seit 2025.",
     [("Charité Berlin", "pilot"), ("Siemens Healthineers", "pilot")]),
    ("We are running a pilot with Lufthansa Technik.", [("Lufthansa Technik", "pilot")]),
    ("Letter of Intent mit Bosch unterzeichnet.", [("Bosch", "loi")]),
    ("Signed an LOI with Schaeffler Group.", [("Schaeffler Group", "loi")]),
    ("Eine Absichtserklärung mit den Stadtwerken München liegt vor.", [("Stadtwerken München", "loi")]),
    ("Designpartner: Trumpf, Festo und Kuka.", [("Trumpf", "design_partner"), ("Festo", "design_partner"), ("Kuka", "design_partner")]),
    ("Forschungspartner ist das Fraunhofer IPA.", [("Fraunhofer IPA", "forschungspartner")]),
    ("Our research partner is TU Berlin.", [("TU Berlin", "forschungspartner")]),
    ("In Zusammenarbeit mit der TU München entwickeln wir den Sensor.", [("TU München", "forschungspartner")]),
    ("Gemeinsam mit Infineon haben wir den Chip integriert.", [("Infineon", "design_partner")]),
    ("Kunden wie Vonovia und LEG Immobilien nutzen die Software.", [("Vonovia", "kunde"), ("LEG Immobilien", "kunde")]),
    ("Zusammen mit der Wärmepumpe ein unschlagbares Team.", []),   # capitalised German noun, not an organisation
    ("Gemeinsam mit Partnern und Kunden entwickeln wir weiter.", []),
])
def test_partner_rules(line, expected):
    result = run(sig(line))
    partners = [(p.name, p.kind) for p in result.fields.get("partners", [])]
    assert partners == expected
    if expected:
        assert all(p.quote == line and str(p.url) == URL for p in result.fields["partners"])
        assert findings(result, "partners") == [line]          # identical evidence is recorded once


def test_partners_dedupe_casefolded_and_skip_own_name():
    result = run(sig("Pilotkunde ist BOSCH.\nLetter of Intent mit Bosch.\nGemeinsam mit KONUX und Siemens Mobility."),
                 name="KONUX GmbH")
    assert [(p.name, p.kind) for p in result.fields["partners"]] == [("BOSCH", "pilot"), ("Siemens Mobility", "design_partner")]


# ----------------------------------------------------------------- regulated market, competitors

@pytest.mark.parametrize("line", [
    "Unser Medizinprodukt der Klasse IIa wird nach MDR zertifiziert.",
    "CE-Kennzeichnung Klasse I ist beantragt.",
    "Das Zulassungsverfahren beim BfArM läuft.",
    "We are preparing our FDA submission.",
    "Als Zahlungsdienstleister unterliegen wir der BaFin.",
    "Wir liefern Prognosen an Netzbetreiber.",
])
def test_regulated_market_rules(line):
    result = run(sig(line))
    assert result.fields["regulated_market"] is True
    assert findings(result, "regulated_market") == [line]


def test_regulated_market_absent_stays_unset():
    assert "regulated_market" not in run(sig("Wir bauen eine App für Hobbygärtner.")).fields


def test_competitors_only_when_named_explicitly():
    result = run(sig("Wettbewerber wie Ada Health und Infermedica setzen auf Apps.\n"
                     "Unlike Celonis, we start from the sensor.\nIm Vergleich zu 80 Prozent der Anbieter sind wir schneller."))
    assert result.fields["competitors"] == ["Ada Health", "Infermedica", "Celonis"]
    assert "competitors" not in run(sig("Der Markt ist umkämpft, es gibt viele Anbieter.")).fields


# ----------------------------------------------------------------- market size, business model

@pytest.mark.parametrize("text, expected", [
    ("Marktvolumen 1,2 Mrd. EUR", 1_200_000_000),
    ("Das Marktvolumen beträgt 1,2 Mrd. EUR in Europa.", 1_200_000_000),
    ("TAM: USD 300 million", 300_000_000),
    ("The addressable market is estimated at $4.5 billion.", 4_500_000_000),
    ("Marktgröße: 750 Mio. Euro", 750_000_000),
])
def test_market_size_rules(text, expected):
    result = run(sig(text))
    assert result.fields["market_size_eur"] == expected
    (finding,) = findings(result, "market_size_eur")
    assert finding.startswith(text)
    assert ("USD 1:1 als EUR" in finding) == ("USD" in text or "$" in text)


def test_market_size_needs_cue_and_unit():
    assert "market_size_eur" not in run(sig("Wir haben 1,2 Mrd. EUR Umsatz.")).fields
    assert "market_size_eur" not in run(sig("Marktvolumen: 1.200 EUR pro Kunde")).fields
    assert parse_money("USD 300 million") == (300_000_000, "USD")
    assert parse_money("1,2 Mrd. EUR") == (1_200_000_000, "EUR")
    assert parse_money("keine Zahl") is None


@pytest.mark.parametrize("line, expected", [
    ("Wir verkaufen B2B an Geschäftskunden.", "b2b"),
    ("Our enterprise customers run the platform on-premise.", "b2b"),
    ("Die App richtet sich an Endkunden und Verbraucher.", "b2c"),
    ("We sell directly to consumers.", "b2c"),
    ("Unser B2B2C-Modell läuft über Versicherer.", "b2b2c"),
])
def test_business_model_rules(line, expected):
    result = run(sig(line))
    assert result.fields["business_model"] == expected
    assert findings(result, "business_model") == [line]


def test_enum_conflict_majority_and_tie():
    majority = run(sig("Wir verkaufen B2B.\nUnsere Geschäftskunden sparen Zeit.\nAuch Endkunden profitieren."))
    assert majority.fields["business_model"] == "b2b"
    assert findings(majority, "business_model") == ["Wir verkaufen B2B.", "Unsere Geschäftskunden sparen Zeit."]
    assert findings(majority, "business_model_alt") == ["Auch Endkunden profitieren."]   # losing line never cites the field
    tie = run(sig("Wir verkaufen B2B.\nWir verkaufen B2B.\nAuch Endkunden profitieren."))   # repeated line counts once
    assert "business_model" not in tie.fields
    assert findings(tie, "business_model") == []
    assert findings(tie, "business_model_alt") == ["Wir verkaufen B2B.", "Auch Endkunden profitieren."]   # deduplicated


def test_product_stage_and_type_rules():
    result = run(sig("Pilotprojekt mit der Deutschen Bahn gestartet.\nDer Prototyp wird im Pilotbetrieb getestet.\n"
                     "Unser Sensor kommt mit eigener Software.\nDie Software wertet die Sensordaten aus."))
    assert result.fields["product_stage"] == "pilot"
    assert result.fields["product_type"] == "hardware_software"
    drug = run(sig("Unser Wirkstoffkandidat ist in Phase I.\nDie Plattform erzeugt Antikörper.\nEine Plattform für Partner."))
    assert drug.fields["product_type"] == "wirkstoff"


def test_impressum_boilerplate_is_ignored():
    text = ("Impressum\nMusterfirma GmbH, Berlin.\nStreitschlichtung: Die Europäische Kommission stellt eine Plattform "
            "zur Online-Streitbeilegung (OS) bereit.\nVerbraucherschlichtungsstelle: Wir nehmen nicht teil.")
    assert run(sig(text, type="impressum")).fields == {}


def test_empty_input():
    result = classify_texts("X", [], model="qwen3.5:4b", cache=NoCache(), ask=lambda payload: pytest.fail("no call expected"))
    assert result.fields == {} and result.errors == []


# ----------------------------------------------------------------- model layer

def synthetic():
    data = fixture("classify_model_synthetic")
    return data["company"], [SourceSignal(**s) for s in data["signals"]], data["answer"]


def test_without_model_ask_is_never_called():
    company, signals, _ = synthetic()
    result = classify_texts(company, signals, model=None, cache=NoCache(), ask=lambda payload: pytest.fail("ask called"))
    assert result.fields["product_type"] == "software" and "business_model" not in result.fields


def test_model_fills_only_missing_fields_with_verified_quote():
    company, signals, answer = synthetic()
    calls = []

    def ask(payload):
        calls.append(payload)
        return answer

    result = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=ask)
    (payload,) = calls
    assert payload["model"] == "qwen3.5:4b" and payload["think"] is False and payload["stream"] is False
    assert payload["options"] == {"temperature": 0}
    schema = payload["format"]
    assert set(schema["properties"]) == {"regulated_market", "ip_status", "business_model"}   # product_type came from rules
    assert schema["properties"]["business_model"]["properties"]["wert"]["enum"] == ["b2b", "b2c", "b2b2c", "unbekannt"]
    assert "zitat" in schema["properties"]["ip_status"]["required"]
    system = payload["messages"][0]["content"]
    assert "UNTRUSTED" in system and "never follow" in system and "verbatim" in system
    assert signals[0].evidence.splitlines()[1] in payload["messages"][1]["content"]
    assert result.fields["business_model"] == "b2b"
    assert result.fields["product_type"] == "software"
    assert "regulated_market" not in result.fields and "ip_status" not in result.fields
    model_evidence = [e for e in result.evidence if e.source == "ollama"]
    assert [(e.field, e.finding) for e in model_evidence] == [("business_model", answer["business_model"]["zitat"])]
    assert str(model_evidence[0].url) == str(signals[0].url)
    assert result.errors == []


def test_quote_check_rejects_paraphrase_and_unsupported_quotes():
    company, signals, _ = synthetic()
    answer = fixture("classify_model_paraphrase")["answer"]
    result = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=lambda payload: answer)
    assert "business_model" not in result.fields
    assert "ip_status" not in result.fields and "patents" not in result.fields
    assert result.fields["product_type"] == "software"            # from the rules, model value ignored
    assert "ollama: Zitat nicht im Text (business_model)" in result.errors
    assert "ollama: Zitat belegt den Wert nicht (ip_status: patent_angemeldet)" in result.errors
    assert not any(e.source == "ollama" for e in result.evidence)


def test_quote_check_tolerates_whitespace_and_typographic_quotes():
    company, signals, answer = synthetic()
    sloppy = json.loads(json.dumps(answer))
    sloppy["business_model"]["zitat"] = "  Unsere   Kunden sind\nproduzierende Unternehmen mit 50 bis 500 Mitarbeitenden, die ihre Energieberichte heute noch in Excel pflegen. "
    result = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=lambda payload: sloppy)
    assert result.fields["business_model"] == "b2b"


def test_enum_rejection_and_malformed_fields():
    company, signals, _ = synthetic()
    answer = fixture("classify_model_invalid")["answer"]
    result = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=lambda payload: answer)
    assert "ip_status" not in result.fields and "business_model" not in result.fields
    assert "regulated_market" not in result.fields                 # "nein" is never recorded
    assert result.fields["product_type"] == "software"
    assert "ollama: ungültiger Wert (ip_status: 'trade_secret')" in result.errors


def test_product_type_from_model_needs_supporting_quote():
    data = fixture("classify_model_quantum_systems")
    signals = [SourceSignal(**s) for s in data["signals"]]
    text, _ = prompt_text(signals)
    quote = "We bring hardware, software and AI together"
    assert quote in text
    plain = SourceSignal(source="Website", type="website", url=signals[0].url, evidence=quote + "\n" + "Our mission is to keep democracies safe and strong.")
    answer = {"product_type": {"wert": "hardware_software", "zitat": quote},
              "business_model": {"wert": "b2b", "zitat": "Our mission is to keep democracies safe and strong."},
              "regulated_market": {"wert": "ja", "zitat": "Our mission is to keep democracies safe and strong."},
              "ip_status": {"wert": "unbekannt", "zitat": ""}}
    # rules see hardware + software on one line -> hardware_software; model is asked only for the rest
    result = classify_texts("Quantum Systems", [plain], model="qwen3.5:4b", cache=NoCache(), ask=lambda p: answer)
    assert result.fields["product_type"] == "hardware_software"
    assert result.fields["regulated_market"] is True
    assert "business_model" not in result.fields           # the quote names no customer group
    assert "ollama: Zitat belegt den Wert nicht (business_model: b2b)" in result.errors
    # a model product_type whose quote names no product type is dropped
    bare = SourceSignal(source="Website", type="website", url=signals[0].url, evidence="Our mission is to keep democracies safe and strong.\nWe are proud of our team.")
    wrong = {"product_type": {"wert": "hardware", "zitat": "Our mission is to keep democracies safe and strong."},
             "business_model": {"wert": "unbekannt", "zitat": ""}, "regulated_market": {"wert": "unbekannt", "zitat": ""},
             "ip_status": {"wert": "unbekannt", "zitat": ""}}
    result = classify_texts("Quantum Systems", [bare], model="qwen3.5:4b", cache=NoCache(), ask=lambda p: wrong)
    assert "product_type" not in result.fields
    assert result.errors == ["ollama: Zitat belegt den Wert nicht (product_type: hardware)"]


def test_recorded_quantum_answer_adds_nothing_without_quotes():
    data = fixture("classify_model_quantum_systems")
    signals = [SourceSignal(**s) for s in data["signals"]]
    result = classify_texts(data["company"], signals, model="qwen3.5:4b", cache=NoCache(), ask=lambda p: data["answer"])
    assert result.fields == {"product_type": "hardware_software"}
    assert result.errors == []


def test_model_error_keeps_rule_results():
    company, signals, _ = synthetic()

    def broken(payload):
        raise OSError("Ollama HTTP 500")

    result = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=broken)
    assert result.fields["product_type"] == "software"
    assert result.errors == ["ollama: Ollama HTTP 500"]
    garbage = classify_texts(company, signals, model="qwen3.5:4b", cache=NoCache(), ask=lambda p: ["not", "an", "object"])
    assert garbage.fields["product_type"] == "software" and garbage.errors == ["ollama: Antwort ist kein JSON-Objekt"]


def test_model_answers_are_cached_per_model_and_prompt(tmp_path):
    company, signals, answer = synthetic()
    cache = Cache(tmp_path / "c.db")
    calls = []

    def ask(payload):
        calls.append(payload["model"])
        return answer

    first = classify_texts(company, signals, model="qwen3.5:4b", cache=cache, ask=ask)
    second = classify_texts(company, signals, model="qwen3.5:4b", cache=cache, ask=ask)
    assert first.fields == second.fields and calls == ["qwen3.5:4b"]
    classify_texts(company, signals, model="other:1b", cache=cache, ask=ask)
    assert calls == ["qwen3.5:4b", "other:1b"]
    keys = sorted(k for (k,) in cache._db().execute("SELECT key FROM cache"))
    assert [k.rsplit(":", 1)[0] for k in keys] == ["classify:other:1b", "classify:qwen3.5:4b"]
    assert all(len(k.rsplit(":", 1)[1]) == 40 for k in keys)


def test_prompt_text_prefers_informative_pages_and_respects_limit():
    nav = sig("Home\nProdukt\nTeam\nKontakt\nImpressum", url="https://example-startup.de/")
    about = sig("Wir entwickeln einen Sensor zur Überwachung von Schweißnähten in der Serienfertigung. " * 3,
                url="https://example-startup.de/ueber-uns")
    long = sig("\n".join(f"Zeile {i}: " + "x" * 80 for i in range(200)), url="https://example-startup.de/news")
    text, used = prompt_text([nav, long, about])
    assert len(text) <= 6000
    assert about in used and long in used and nav not in used      # the long page does not crowd out the about page
    assert "Home\nProdukt" not in text and "Zeile 199" not in text
    only_nav, used = prompt_text([nav])
    assert used == [nav] and "Produkt" in only_nav
    assert set(build_schema(MODEL_FIELDS)["properties"]) == set(MODEL_FIELDS)
    assert "market_size_eur" not in MODEL_FIELDS and "partners" not in MODEL_FIELDS and "product_stage" not in MODEL_FIELDS


# ----------------------------------------------------------------- scope, plans, alternatives (fact-check regressions)

from context.idw import parse_article  # noqa: E402


def idw_signal(news_id, source="idw"):
    art = parse_article((FIXTURES / f"idw_news{news_id}.html").read_text(encoding="utf-8"))
    return SourceSignal(source=source, type="idw", url=f"https://idw-online.de/de/news{news_id}", date=art["date"],
                        evidence=art["title"] + "\n" + art["body"])


def test_round_up_text_is_scoped_to_lines_naming_the_lead_or_a_founder():
    text = ("Hochschule zeigt Innovationen auf der Messe\n"
            "Das Start-up Alpha Robotics hat ein Patent erteilt bekommen und betreibt ein Pilotprojekt mit der Deutschen Bahn.\n"
            "Die Ausgründung Beispiel Energie zeigt ihren Sensor für Wärmenetze.\n"
            "Der Prototyp wird am Stand vorgeführt.\n"
            "Die Gruppe von Prof. Weber forscht an Antikörpern und Wirkstoffen.\n"
            "Kim Muster erklärt: Unser B2B-Vertrieb startet 2027.")
    press = sig(text, url="https://uni.example/presse/messe", type="idw", source="idw")
    result = classify_texts("Beispiel Energie GmbH", [press], model=None, cache=NoCache(), founders=["Kim Muster"])
    assert "ip_status" not in result.fields and "patents" not in result.fields and "partners" not in result.fields
    assert result.fields["product_stage"] == "prototyp"           # the line after the mention is read as well
    assert result.fields["product_type"] == "hardware"
    assert result.fields["business_model"] == "b2b"               # founder surname line
    assert all("Alpha Robotics" not in e.finding and "Antikörper" not in e.finding for e in result.evidence)
    # the same text is read completely when the title names the lead or the name occurs twice
    whole = classify_texts("Alpha Robotics", [sig("Alpha Robotics auf der Messe\n" + text, type="idw", source="idw")],
                           model=None, cache=NoCache())
    assert whole.fields["ip_status"] == "patent_erteilt" and whole.fields["partners"][0].name == "Deutschen Bahn"
    flagged = classify_texts("Alpha Robotics", [sig("Alpha Robotics auf der Messe\n" + text, type="idw", source="idw (Erwähnung)")],
                             model=None, cache=NoCache())
    assert "partners" in flagged.fields and flagged.fields["ip_status"] == "patent_erteilt"   # its own lines still count
    assert "product_type" in flagged.fields and "Antikörper" not in " ".join(e.finding for e in flagged.evidence)


def test_plan_sentences_never_yield_stage_regulation_partners_or_ip():
    lines = ["Für die Zukunft planen die Gründer, ihr Produkt auch für die medizinische Diagnostik anzupassen.",
             "Wir wollen 2027 ein Pilotprojekt mit der Deutschen Bahn starten.",
             "The team plans to file a patent next year.",
             "Eine Zulassung als Medizinprodukt wäre denkbar.",
             "Der Sensor soll künftig an Netzbetreiber geliefert werden."]
    result = run(sig("\n".join(lines)))
    assert not {"product_stage", "regulated_market", "partners", "ip_status", "patents"} & set(result.fields)
    # a factual sentence next to a plan sentence in the same paragraph still counts
    mixed = run(sig("Unser Pilotprojekt mit der Deutschen Bahn läuft. Wir wollen 2027 weitere Pilotkunden gewinnen."))
    assert mixed.fields["product_stage"] == "pilot" and mixed.fields["partners"][0].name == "Deutschen Bahn"


@pytest.mark.parametrize("line, stage", [
    ("Read the white paper", None),
    ("Our white paper walks through real characterization scenarios.", None),
    ("Laden Sie das Datenblatt und das Whitepaper herunter.", None),
    ("Our paper was published in Nature Physics.", "paper"),
    ("Das Paper wurde auf der Konferenz vorgestellt.", "paper"),
    ("Die Publikation beschreibt das Verfahren.", "paper"),
    ("The plan is to acquire the first pilot customers to test it.", None),
    ("Wir suchen Pilotkunden für 2027.", None),
    ("Er identifizierte Olivenölhersteller und Brauereien als Pilotkunden.", None),
    ("Pilotkunden sind die Stadtwerke Köln.", "pilot"),
    ("Das Verfahren wurde in den Pilotmaßstab übertragen.", "pilot"),
])
def test_stage_rules_paper_and_pilot_plans(line, stage):
    result = run(sig(line))
    assert result.fields.get("product_stage") == stage


def test_website_market_cues_outrank_press_stage():
    site = sig("Pricing\nOrder now\nUnsere Kunden weltweit vertrauen auf das System.", url="https://example-startup.de/")
    press = sig("Beispiel Energie zeigt Prototyp\nDer Prototyp wurde vorgestellt.\nDer Prototyp misst Wärme.\nEin Laborprototyp existiert.",
                url="https://uni.example/news", type="idw", source="idw")
    result = run(press, site)
    assert result.fields["product_stage"] in {"am_markt", "erste_kunden"}
    assert all("Prototyp" not in f for f in findings(result, "product_stage"))
    assert any("Prototyp" in f for f in findings(result, "product_stage_alt"))
    assert run(press).fields["product_stage"] == "prototyp"      # press alone decides when no website exists
    weak = run(sig("Wir mieten Büros in Berlin.", url="https://uni.example/news", type="idw", source="idw"))
    assert "product_stage" not in weak.fields                     # shop cues only count on the company's own pages


def test_wirkstoff_needs_pharma_lines_and_molecules_are_not_drugs():
    sensor = run(sig("Der Sensor erkennt reaktionsfreudige Moleküle.\nFreie Radikale sind Moleküle mit ungepaarten Elektronen.\n"
                     "Das Gerät passt in eine Hand.\nAnwendungen in der Arzneimittelentwicklung sind denkbar: drug development."))
    assert sensor.fields["product_type"] == "hardware"
    assert "Freie Radikale sind Moleküle" not in " ".join(e.finding for e in sensor.evidence)   # no wirkstoff hit at all
    drug = run(sig("Unser Wirkstoffkandidat ist in Phase I.\nDie Plattform erzeugt Antikörper.\nEine Plattform für Partner."))
    assert drug.fields["product_type"] == "wirkstoff"
    assert findings(drug, "product_type") == ["Unser Wirkstoffkandidat ist in Phase I.", "Die Plattform erzeugt Antikörper."]
    assert findings(drug, "product_type_alt") == ["Die Plattform erzeugt Antikörper.", "Eine Plattform für Partner."]
    one_line = run(sig("Wir entwickeln einen Wirkstoff gegen Malaria.\nDas Team sitzt in Berlin."))
    assert "product_type" not in one_line.fields                  # a single pharma line is not enough


def test_only_the_winning_value_carries_the_field_name():
    result = run(sig("Unser Medizinprodukt der Klasse IIa wird nach MDR zertifiziert.\nDer Prototyp wird getestet.\n"
                     "Der Prototyp läuft im Labor.\nUnser MVP ist fertig."))
    assert result.fields["product_stage"] == "prototyp"
    assert findings(result, "product_stage") == ["Der Prototyp wird getestet.", "Der Prototyp läuft im Labor."]
    assert findings(result, "product_stage_alt") == ["Unser MVP ist fertig."]
    assert findings(result, "regulated_market") == ["Unser Medizinprodukt der Klasse IIa wird nach MDR zertifiziert."]
    duplicated = run(sig("Patentierte Technologie.\nPatentierte Technologie.\nPatentierte Technologie."))
    assert findings(duplicated, "ip_status") == ["Patentierte Technologie."]
    assert findings(duplicated, "patents") == ["Patentierte Technologie."]
    assert len(duplicated.fields["patents"]) == 1                 # one patent per status and source


@pytest.mark.parametrize("line, regulated", [
    ("Die Forschung an Diagnostik und Arzneimitteln ist teuer.", False),
    ("Medizin ist ein großer Markt.", False),
    ("Unser Diagnostik-System analysiert Blutproben.", True),
    ("Our product is used in Arzneimittel manufacturing.", True),
    ("Wir planen den Einsatz unseres Systems in der Diagnostik.", False),
    ("Das Gerät ist ein Medizinprodukt der Klasse IIa.", True),
    ("Wir liefern Prognosen an Netzbetreiber.", True),
])
def test_weak_regulated_cues_need_the_product_itself(line, regulated):
    assert (run(sig(line)).fields.get("regulated_market") is True) == regulated


def test_partner_kind_pilot_and_publisher_exclusion():
    line = ("Nach erfolgreichen Tests im Labormaßstab folgte 2025 der nächste Schritt: Gemeinsam mit dem Halbleiterhersteller "
            "Freiberger Compound Materials (FCM) GmbH übertrug das Beispiel-Team die Technologie in den Pilotmaßstab.")
    result = run(sig(line))
    assert [(p.name, p.kind) for p in result.fields["partners"]] == [("Freiberger Compound Materials", "pilot")]
    plant = run(sig("In Zusammenarbeit mit der TU München betreiben wir eine Pilotanlage."))
    assert [(p.name, p.kind) for p in plant.fields["partners"]] == [("TU München", "pilot")]
    # the publishing university (named in the title / source) is never a partner of its own spin-off
    press = sig("Universität Stuttgart auf der Hannover Messe\nBeispiel Energie präsentiert den Sensor.\n"
                "Gemeinsam mit der Universität Stuttgart und Bosch GmbH hat Beispiel Energie den Sensor entwickelt.",
                url="https://uni.example/news", type="idw", source="idw")
    partners = run(press).fields.get("partners", [])
    assert [p.name for p in partners] == ["Bosch GmbH"]
    # "gemeinsam mit" lines only count when the line itself is about the lead
    other = sig("Messebericht\nBeispiel Energie zeigt den Sensor.\nDie KSat-Gruppe arbeitet gemeinsam mit der ESA an Satelliten.",
                url="https://uni.example/news", type="idw", source="idw")
    assert "partners" not in run(other).fields


def test_model_prompt_prefers_own_pages_and_never_quotes_catalogue_rows():
    foekat = sig("Thema: Beispiel Energie; Förderempfänger: Universität X; Laufzeit 2024-2026; Ausführende Stelle: Institut Y.",
                 url="https://foerderportal.bund.de/foekat/x", type="exist_projekt", source="Förderkatalog")
    press = sig("Beispiel Energie erhält Förderung\nDas Start-up verkauft B2B an Geschäftskunden und Industriebetriebe im ganzen Land.",
                url="https://uni.example/news", type="idw", source="idw")
    site = sig("Wir entwickeln einen Sensor zur Überwachung von Schweißnähten in der Serienfertigung für Industriekunden.",
               url="https://example-startup.de/produkt")
    text, used = prompt_text([foekat, press, site], name="Beispiel Energie GmbH")
    assert used == [site, press] and "Förderkatalog" not in text and text.index("Schweißnähten") < text.index("B2B")
    assert prompt_text([foekat], name="Beispiel Energie GmbH") == ("", [])
    answer = {"regulated_market": {"wert": "unbekannt", "zitat": ""},
              "ip_status": {"wert": "patent_angemeldet", "zitat": "Patent angemeldet."},
              "business_model": {"wert": "b2c", "zitat": "Millikelvin without buying a cryostat: send us a sample, or rent a system in Munich."}}
    cryo = sig("Millikelvin without buying a cryostat: send us a sample, or rent a system in Munich.\nWir bauen Kryostaten für Labore.")
    result = classify_texts("Beispiel Energie GmbH", [foekat, cryo], model="qwen3.5:4b", cache=NoCache(), ask=lambda p: answer)
    assert "ip_status" not in result.fields and "business_model" not in result.fields
    assert "ollama: Zitat nicht im Text (ip_status)" in result.errors
    assert "ollama: Zitat belegt den Wert nicht (business_model: b2c)" in result.errors
    ok = {"business_model": {"wert": "b2c", "zitat": "Wir verkaufen direkt an Verbraucher."},
          "regulated_market": {"wert": "unbekannt", "zitat": ""}, "ip_status": {"wert": "unbekannt", "zitat": ""}}
    consumer = classify_texts("Beispiel Energie GmbH", [sig("Wir verkaufen direkt an Verbraucher.\nUnser Shop ist offen.")],
                              model="qwen3.5:4b", cache=NoCache(), ask=lambda p: ok)
    assert consumer.fields["business_model"] == "b2c"


# ----------------------------------------------------------------- recorded leads (fact-check expectations)

def test_spinmagic_is_a_hardware_prototype_without_pilots_or_regulation():
    """idw news849480 (trade-fair round-up), news839134 and news844318 (both about SpinMagIC)."""
    signals = [idw_signal(849480), idw_signal(839134), idw_signal(844318)]
    result = classify_texts("SpinMagIC", signals, model=None, cache=NoCache(),
                            founders=["Jens Anders", "Belal Alnajjar", "Anh Chu", "Michele Segantini"])
    assert result.fields.get("product_type") in {"hardware", None}
    assert "regulated_market" not in result.fields
    assert result.fields.get("product_stage") in {"prototyp", None}
    assert "partners" not in result.fields and "ip_status" not in result.fields
    # nothing from the round-up's other exhibitors (KSat, IntCDC) is cited for any field
    cited = [e.finding for e in result.evidence if str(e.url).endswith("849480")]
    assert cited and all("SpinMagIC" in f for f in cited)
    assert all("Pilotkunden" not in f for f in findings(result, "product_stage"))


def test_kiutra_sells_systems_and_blickfeld_patents_are_not_kiutras():
    data = fixture("classify_kiutra_signals")
    signals = [SourceSignal(**s) for s in data["signals"]]
    result = classify_texts(data["company"], signals, model="qwen3.5:4b", cache=NoCache(),
                            ask=lambda payload: data["model_answer"], founders=data["founders"])
    assert result.fields["product_stage"] in {"erste_kunden", "am_markt"}
    assert all("white paper" not in f.lower() for f in findings(result, "product_stage"))
    assert result.fields.get("business_model") in {"b2b", None}
    assert "ip_status" not in result.fields and "patents" not in result.fields
    assert not any(str(e.url).endswith("718959") and "Blickfeld" in e.finding for e in result.evidence)
    assert result.fields["product_type"] == "hardware"
    # the model never saw the Blickfeld lines, so its patent quote fails the substring check
    assert "ollama: Zitat nicht im Text (ip_status)" in result.errors
    assert "ollama: Zitat belegt den Wert nicht (business_model: b2c)" in result.errors


def test_siderogain_pilot_plant_with_fcm_and_one_granted_patent():
    result = classify_texts("Siderogain", [idw_signal(876491)], model=None, cache=NoCache(), founders=["Rohan Jain"])
    assert [(p.name, p.kind) for p in result.fields["partners"]] == [("Freiberger Compound Materials", "pilot")]
    assert result.fields["product_stage"] == "pilot"
    assert result.fields["ip_status"] == "patent_erteilt"
    assert [p.status for p in result.fields["patents"]] == ["patent_erteilt"]
    assert len(findings(result, "patents")) == len(set(findings(result, "patents")))
    assert result.fields.get("product_type") in {None, "hardware"}
    assert "regulated_market" not in result.fields
