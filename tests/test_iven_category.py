"""Category "Höheres Risiko": Iven's 34 registered companies next to our 52 EXIST leads, never merged."""
import csv
import json
import time
from pathlib import Path

import pytest

from demo_snapshot.iven_adapter import IVEN_PATH, REFERENCE, build_iven, load_iven

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not IVEN_PATH.exists(), reason="iven_companies.json not built")


def _longlist():
    with (ROOT / "Ergebnisse/Longlist.csv").open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream, delimiter=";"))[1:]


def test_adapter_copies_ivens_values_exactly():
    data = load_iven.__wrapped__()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert data["rule_version"] == reference["rule_version"] == "early-stage.2"
    assert data["source_snapshot_date"] == reference["source_snapshot_date"]
    assert len(data["companies"]) == 34
    for company, item in zip(data["companies"], reference["assessments"]):
        assert company["id"] == item["dossier"]["id"]
        for ours, his in (("score", "score"), ("score_upper", "score_upper"), ("company_score", "company_score"),
                          ("market_score", "market_score"), ("risk", "risk"), ("stage", "stage"),
                          ("queue", "queue"), ("coverage", "coverage"), ("htgf_fit", "htgf_fit")):
            assert company[ours] == item[his], (company["name"], ours)
        assert [c["points"] for c in company["criteria"]] == [c["points"] for c in item["criteria"]]
    number = lambda v: "" if v is None else str(v)
    rows = _longlist()
    assert [[c["name"], ", ".join(c["sectors"]), c["status"], number(c["score"]), c["risk"], number(c["market_score"]),
             number(c["company_score"]), c["stage"], c["summary"], c["thesis"]] for c in data["companies"]] == rows


def test_build_is_reproducible_and_redacts_personal_emails(tmp_path):
    out = build_iven(REFERENCE, tmp_path / "iven.json")
    built = json.loads(out.read_text(encoding="utf-8"))
    frozen = json.loads(IVEN_PATH.read_text(encoding="utf-8"))
    assert built == frozen
    text = out.read_text(encoding="utf-8")
    assert "i@nunrie-technology.de" not in text and "[E-Mail entfernt]" in text
    assert "info@refactum.de" in text   # generic company mailbox stays


def test_both_datasets_load_fast():
    from demo_snapshot import load_snapshot
    start = time.perf_counter()
    load_snapshot.__wrapped__()
    load_iven.__wrapped__()
    assert time.perf_counter() - start < 3


def test_filters_keep_ivens_order_and_linkedin():
    from urllib.parse import unquote

    import iven_view
    data = load_iven()
    companies = data["companies"]
    ranked = iven_view.filter_companies(companies, status="Bewertbar")
    assert [c["rank"] for c in ranked] == sorted(c["rank"] for c in ranked) and len(ranked) == 8
    health = iven_view.filter_companies(companies, sector="HealthTech")
    assert health and all("HealthTech" in c["sectors"] for c in health)
    refactum = companies[0]
    assert refactum["name"] == "REFACTUM GmbH" and refactum["score"] == 69.0
    label, url, found = iven_view.linkedin(refactum["team"][0], refactum)
    assert found and url.startswith("https://www.linkedin.com/in/")
    label, url, found = iven_view.linkedin({"name": "Erika Muster", "linkedin": None}, refactum)
    assert not found and unquote(url).endswith("keywords=Erika Muster REFACTUM GmbH")
    assert iven_view.mailto(refactum).startswith("mailto:info@refactum.de?")


def test_ymolution_cross_reference():
    import iven_view
    from demo_snapshot import load_snapshot
    run, _ = load_snapshot()
    ymo = next(c for c in load_iven()["companies"] if c["name"] == "Ymolution GmbH")
    assert [x.name for x in iven_view.also_early(ymo, run.result.leads)] == ["Ymolution"]


def _snapshot_app():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    next(b for b in app.button if b.label == "Analyse starten").click().run()
    assert not app.exception
    return app


def test_category_switch_shows_separate_rankings():
    import iven_view
    app = _snapshot_app()
    category = next(x for x in app.get("button_group") if x.label == "Kategorie") if app.get("button_group") else None
    assert category is not None
    assert "Snapshot · echte Leads" in " ".join(str(x.value) for x in app.markdown)
    category.set_value(iven_view.CATEGORY_RISK).run()
    assert not app.exception
    text = " ".join(str(x.value) for x in app.markdown) + " ".join(str(x.value) for x in app.caption)
    assert "Firmen-Radar, Regelwerk early-stage.2, Stand 21.11.2026" in text
    assert "nicht vergleichbar" in " ".join(str(x.value) for x in app.info)
    assert len(app.dataframe) == 1
    frame = app.dataframe[0].value
    assert list(frame["Unternehmen"])[:2] == ["REFACTUM GmbH", "Fibryx GmbH"]
    assert "Snapshot · echte Leads" not in text   # our EXIST ranking is not rendered in this category


def test_every_iven_deep_dive_renders():
    from streamlit.testing.v1 import AppTest
    data = load_iven()
    start = time.perf_counter()
    for company in data["companies"]:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        app.query_params["iven"] = company["id"]
        app.run()
        assert not app.exception, company["name"]
        assert company["name"] in " ".join(str(x.value) for x in app.title)
        html = " ".join(str(x.value) for x in app.markdown)
        assert "Investmenthypothese" in html
    assert time.perf_counter() - start < 120
