"""Snapshot mode ("Snapshot (echte Leads)"): frozen real run, every view, no network."""
import time
from datetime import date
from pathlib import Path

import pytest

from demo_snapshot import ANALYSIS_PATH, load_snapshot

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not ANALYSIS_PATH.exists(), reason="demo_snapshot not built")


def snapshot_app():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert next(x for x in app.radio if x.label == "Datenquelle").value == "snapshot"
    assert not any(x.label == "Kategorie" for x in app.radio)
    next(b for b in app.button if b.label == "Analyse starten").click().run()
    assert not app.exception
    return app


def test_snapshot_loads_fast_and_is_real():
    start = time.perf_counter()
    run, meta = load_snapshot.__wrapped__()
    assert time.perf_counter() - start < 3
    leads = run.result.leads
    assert run.mode == "live" and len(leads) >= 50
    assert not any(x.is_demo for x in leads)
    assert all(str(x.source_url).startswith("https://foerderportal.bund.de/") for x in leads)
    assert meta["kind"] == "snapshot" and set(meta["leads"]) == {x.id for x in leads}
    assert meta["backtest"]["headline"].startswith("11/11 früh erkannt")
    best = meta["best_find"]
    assert best["name"] == "Ymolution" and best["lead_id"] in meta["leads"]
    assert len(best["timeline"]) >= 5 and all(r["source"] or r["source_note"] for r in best["timeline"])
    assert any(r["name"] == "InhalPlus" for r in best["rejected"])


def test_parse_best_find_and_backtest_meta():
    from demo_snapshot.build_snapshot import parse_best_find

    text = """## 1. Foo (FKZ 03EF0001)

Intro satz. Rang 3 von 9.

| Datum | Signal | Quelle |
|---|---|---|
| **01.01.2025** | **Start** (unser Signal) | https://example.org/a |
| heute | Ohne Link | Gegensuche |

**Team:** A, B.
**Warum jetzt anrufen:** weil.
**Offen:** X.

## Gestrichen: Bar (FKZ 03EF0002)

Finanziert (https://example.org/b).
"""
    best = parse_best_find(text)
    assert (best["name"], best["fkz"], best["lead_id"]) == ("Foo", "03EF0001", "foekat-03ef0001")
    assert best["intro"] == "Intro satz."
    assert best["timeline"][0] == {"when": "01.01.2025", "signal": "Start (unser Signal)",
                                   "source": "https://example.org/a", "source_note": None}
    assert best["timeline"][1]["source_note"] == "Gegensuche"
    assert (best["team"], best["why_now"], best["open"]) == ("A, B.", "weil.", "X.")
    assert best["rejected"] == [{"name": "Bar", "fkz": "03EF0002", "reason": "Finanziert (https://example.org/b).",
                                 "source": "https://example.org/b"}]


def test_earliness_helpers():
    from dashboard import db_status, founder_names, lead_time_months, stage_label
    from deep_dive import signal_timeline

    run, meta = load_snapshot()
    lead = next(x for x in run.result.leads if x.name == "Ymolution")
    assert db_status(lead) == ("kein DB-Profil (Wayback/Datenbanksuche)", "good")
    assert founder_names(lead)[:2] == ["Alexander Reder", "Christian Hentschker"]
    assert stage_label(lead, meta) == "Pre-Seed"
    assert lead_time_months(lead, meta) == meta["leads"][lead.id]["earliness_delta_monate"]
    stripped = lead.model_copy(update={"first_signal_date": date(2024, 11, 1), "in_databases": False})
    assert lead_time_months(stripped, None, date(2026, 11, 21)) == 24
    events = signal_timeline(lead, date(2026, 11, 21))
    first = next(e for e in events if e[4])
    assert first[0] == date(2024, 11, 1) and "Förderbeginn" in first[1] and "foerderportal" in first[3]
    assert [e[0] for e in events] == sorted(e[0] for e in events)
    assert any("endete" in e[1] for e in events)


def test_snapshot_overview_filters_and_best_find():
    app = snapshot_app()
    run, meta = load_snapshot()
    assert any("SNAPSHOT" in x.value for x in app.caption)
    assert len(app.dataframe[0].value) == 10
    assert len(app.get("plotly_chart")) == 4  # 3D, stages, comparison, backtest
    assert any("Best Find" in x.value for x in app.markdown)
    assert any(x.value == "Noise und Abgelehnt" for x in app.subheader)
    assert any("Gestrichen: InhalPlus" in x.value for x in app.warning)
    table = app.dataframe[0].value
    assert {"Website", "Gründer", "Erstes Signal", "DB-Check", "Vorsprung", "Branche", "Stage"} <= set(table.columns)

    next(x for x in app.toggle if x.label == "Nur ohne DB-Profil").set_value(True).run()
    assert not app.exception
    names = set(app.dataframe[0].value["Unternehmen"])
    assert all(x.in_databases is False for x in run.result.leads if x.name in names)
    next(x for x in app.selectbox if x.label == "Branche").set_value("HealthTech").run()
    assert not app.exception
    assert set(app.dataframe[0].value["Branche"]) == {"HealthTech"}
    next(x for x in app.toggle if x.label == "Nur ohne DB-Profil").set_value(False).run()
    next(x for x in app.selectbox if x.label == "Branche").set_value("Alle Branchen").run()
    next(x for x in app.selectbox if x.label == "Ranking anzeigen").set_value(50).run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 50

    next(x for x in app.button if x.key == "best_find_open").click().run()
    assert not app.exception
    assert app.title[0].value == "Ymolution"
    assert any(x.value == "Signal-Zeitleiste" for x in app.subheader)
    next(x for x in app.button if x.key == "back_to_portfolio").click().run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 50  # Top-N kept
    next(x for x in app.button if x.label == "Neue Analyse").click().run()
    assert not app.exception and not app.dataframe


def test_every_snapshot_deep_dive_renders():
    from ui_theme import md_escape

    app = snapshot_app()
    run, _ = load_snapshot()
    for lead in run.result.leads:
        app.query_params["startup"] = lead.id
        app.run()
        assert not app.exception, lead.id
        assert app.title[0].value == md_escape(lead.name)
        assert any(x.value == "Team" for x in app.subheader)
        assert any(x.label == "Quellen & Belege" for x in app.tabs)


def test_build_snapshot_reproduces_from_dossiers(tmp_path):
    from demo_snapshot.build_snapshot import DEFAULT_DOSSIERS, build
    from models import AnalysisRun

    if not DEFAULT_DOSSIERS.exists():
        pytest.skip("loop-1 dossiers (AGENT_TEAM/reports/scratch, not versioned) missing")
    analysis_path, meta_path = build(DEFAULT_DOSSIERS, tmp_path)
    run = AnalysisRun.model_validate_json(analysis_path.read_text(encoding="utf-8"))
    frozen, _ = load_snapshot()
    assert {x.id for x in run.result.leads} == {x.id for x in frozen.result.leads}
    assert run.created_at == frozen.created_at


def test_linkedin_profile_or_search_per_person():
    """Team card and contact box: the public profile from context/team.py, else a people search; links only."""
    from urllib.parse import unquote

    from dashboard import founder_names, linkedin_link, linkedin_profile
    from demo_snapshot import load_snapshot

    run, _ = load_snapshot()
    leads = {x.name: x for x in run.result.leads}
    bot = leads["BotFellows"]
    assert linkedin_profile(bot, "Jayanto Halim") == "https://www.linkedin.com/in/jayanto-halim/"
    label, url, found = linkedin_link(bot, "Jayanto Halim")
    assert (label, found) == ("LinkedIn", True)
    for lead in run.result.leads:
        for name in founder_names(lead):
            label, url, found = linkedin_link(lead, name)
            assert url.startswith("https://") and "linkedin.com/" in url
            if not found:
                assert label == "Auf LinkedIn suchen"
                assert unquote(url).endswith(f"keywords={name} {lead.name}")
    assert linkedin_profile(bot, "Niemand Erfunden") is None


def test_linkedin_buttons_in_deep_dive():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    app.query_params["startup"] = "foekat-03efmv0034"   # Ymolution
    app.run()
    assert not app.exception
    html = " ".join(str(x.value) for x in app.markdown)
    assert 'target="_blank"' in html and ("LinkedIn" in html)
