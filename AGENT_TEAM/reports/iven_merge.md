# Ivens Firmen-Suche im Dashboard (`iven-merge`), Stand 21.11.2026

Branch `agents/iven-companies` (von main @ 3a1e7de). Lokal committet, **nicht gepusht**.

| Commit | Inhalt |
|---|---|
| `5430ef2` | Merge `f798e7b` (= `origin/feature/founderradar-investment-cockpit`, 8 Commits) |
| (folgt) | Reproduktions-Check, Adapter, Kategorie „Höheres Risiko“, Snapshot-Build, Tests, dieser Bericht |

## Ergebnis

- **Reproduktion: 34/34 Firmen identisch.** Geprüft wurden Score, Obergrenze, Unternehmens-, Markt- und Nachweis-Score, Risiko, Stage, Queue, Datenabdeckung, Hypothese, HTGF-Fit und nächste Schritte. Die Reihenfolge ist identisch. `Ergebnisse/Longlist.csv` stimmt in **34/34 Zeilen** mit allen 10 Spalten überein, die Texte eingeschlossen. Zähler: 8 bewertbar, 26 Recherche offen, 0 ausgeschlossen. 0 Webabrufe, 0 LLM-Aufrufe. REFACTUM: 69,0 (85/50/70).
- **Tests:** `pytest -q` ergibt **1005 passed, 1 skipped**. `pytest AGENT_TEAM/eval` ergibt **15 passed**, die Reproduktion eingeschlossen. Ivens Tests (`test_mvp`, `test_mvp_briefs`, `test_project_ai`, `test_live_demonstration`, `test_combined_discovery`, `test_free_discovery`): 85 passed, 1 skipped (Begründung unten).
- **AppTest ohne Exception:**
  - beide Kategorien im Radar
  - alle **34 Deep Dives** von Ivens Firmen (`?iven=<id>`)
  - Ivens eigenes Cockpit (`FOUNDERRADAR_UI=mvp`, Klick auf „Score jetzt berechnen“ ergibt Replay 8/26, 0 Webabrufe, REFACTUM 69,0)
  - Unsere 52 Deep Dives laufen über die bestehenden Tests weiter.
- **Smoke headless auf Port 8599:**
  - `app.py`: `/_stcore/health` = ok, `/?view=snapshot` = 200, `/?iven=company-acb1c3cd21aa0fcaa3a0` = 200
  - `cockpit.py` (mvp): health ok, Seite 200
  - Beide Server danach gestoppt. Der Server auf 8501 lief unverändert weiter.

## 1. Merge-Entscheidungen

Ausgangslage: `f798e7b` hat zwei Merge-Basen mit main (fda6207, 1d142ee). Die Konflikte stammen fast nur aus Ivens Merge-Commit eca9b14. Dort hat er Dateien aufgelöst, die wir bei der letzten Integration schon bewusst anders zusammengeführt hatten. Neu bei Iven sind vor allem `mvp/` und die Datenpakete.

| Bereich | Entscheidung |
|---|---|
| `mvp/` (21 Module), `data/mvp/` (jury-reference, demo-run), `data/combined-discovery.json`, `data/open-discovery/`, `Ergebnisse/`, `config/early_stage.v2.json`, `config/company_briefs.json`, `config/project_sources.json`, `config/team_sources.json`, `free_discovery/`, `sourcing/combined.py`, `sourcing/open_data.py`, `batch_analysis.py`, Launcher (`launch_founderradar.py`, `Start-*.cmd/.ps1`, `Ergebnisse-aktualisieren.cmd`, `Dockerfile.relay`), Doku (`JURY-HANDOFF.md`, `START-UND-TESTANLEITUNG.md`, `PITCH-TUTORIAL.md`, `ABGABE.txt`, `MVP-START.txt`, `START-DEMO.txt`, docs/*), Tests | **vollständig übernommen** |
| `context/engine.py`, `evaluation/engine.py` (automatisch gemergt) | **auf unsere Version zurückgesetzt**. Ivens Änderungen hätten den `labelled()`-Fix und den `first_signal_date`-Ausschluss rückgängig gemacht und die Quelle von `beschreibung_rohtext` geändert. Diese Quelle nutzt `dated_fact` im Scoring. |
| `demo_portfolio.py`, `examples/market-input-schema.json`, `tests/test_context_engine.py`, `tests/test_screening.py`, `tests/test_context.py`, `tests/test_cockpit.py` (automatisch gemergt) | **unsere Version**. Der Auto-Merge hätte Felder und Tests aus unserer Integration entfernt. |
| `app.py`, `dashboard.py`, `deep_dive.py`, `pipeline.py`, `models.py`, `.streamlit/config.toml`, `examples/analysis-*.json`, `examples/context-schema.json`, `tests/test_dashboard.py` (Konflikte) | **unsere Version als Basis** (Integration 21c69f1), dazu additiv: |
| ↳ `models.py` | `AnalysisRun.discovery: dict \| None = None`. Ivens `mvp.handoff` braucht das Feld. Schema `examples/analysis-schema.json` neu erzeugt. |
| ↳ `pipeline.py` | `FOUNDERRADAR_SOURCING=foekat\|combined\|open_data`. **Standard bleibt `foekat`**, also unser Förderkatalog. Ivens kombinierte Suche lässt sich zuschalten. Die `discovery`-Provenienz wird bis in `AnalysisRun` durchgereicht. |
| `analyst_store.py`, `cockpit.py`, `README.md`, `.gitignore` | Ivens spätere Deltas: `db_path()`, `cockpit.py` startet standardmäßig `mvp.cockpit`, mit `FOUNDERRADAR_UI=classic` den Bestandsweg. Dazu der Abgabe-Abschnitt im README und Runtime-Pfade in `.gitignore`. |
| `cockpit_service.py`, `requirements.txt` (`requests`, `beautifulsoup4`), `tests/test_workspace.py` (Fixture `FOUNDERRADAR_UI=classic`), `tests/test_pipeline.py`, `tests/test_sourcing_edge.py` | Ivens Version (additiv) |
| `tests/test_combined_discovery.py::test_description_points_to_company_source_not_identity_api` | **skip mit Begründung**. Der Test prüft Ivens `to_dossier`-Änderung, die wir nicht übernehmen (Regel: Datenlogik bleibt unsere). |

Unser Snapshot wurde danach neu gebaut. Die 52 Leads sind inhaltlich byte-identisch. Neu ist nur `"discovery": null` und ein anderes `built_at`.

**Hinweis zu „Regelwerk v13“:** Ivens Daten enthalten keine Version 13. Der Referenzlauf trägt `rule_version: "early-stage.2"` (`config/early_stage.v2.json`, `schema_version mvp.1`, `resolver_version 2`). Das UI zeigt deshalb den echten Wert: „Ivens Firmen-Suche, Regelwerk early-stage.2, Stand 21.11.2026“.

## 2. Reproduktion

`AGENT_TEAM/eval/check_iven_reproduction.py` (Test: `AGENT_TEAM/eval/test_iven_reproduction.py`):

- Das Skript rechnet `mvp.engine.run(RunOptions(mode="replay", …))` genau wie Ivens Button „Score jetzt berechnen“.
- Der Stichtag ist fix auf `as_of` des Referenzlaufs gesetzt (21.11.2026), nicht auf `date.today()`. Sektoren, 24-Monats-Fenster und Limit kommen ebenfalls aus der Referenz.
- Geschrieben wird in ein temporäres `FOUNDERRADAR_MVP_DATA`. Ohne `latest.json` lädt `load_last()` dann `data/mvp/jury-reference.json`.
- Verglichen wird pro Firma, mit der Reihenfolge und mit der Longlist. Die Longlist-Zeilen entstehen wie in `mvp/export_jury.py` über `brief_for(item, live=True)`. Im Repo liegen keine KI-Insights.
- Einzige Abweichung: `reasons` bei den 7 Firmen, deren Live-Abruf fehlschlug. Replay setzt `refresh_status = "snapshot"`, deshalb fällt die Zeile „Aktuelle Website-Prüfung fehlgeschlagen…“ weg. Das ist Ivens Design und ändert weder Queue noch Score. Das Skript prüft, dass das die einzige Abweichung ist.

```
34/34 Firmen identisch, Longlist 34/34 Zeilen identisch, Reihenfolge identisch: OK
```

## 3. Wie die Kategorie im UI aussieht

- **Radar-Ansicht, oben:** ein neuer Umschalter „Kategorie“ (Pill-Buttons) mit zwei Werten:
  - **„Frühe Vorhaben (EXIST, vor Gründung)“** (Standard): unser Dashboard mit den 52 Leads, unverändert.
  - **„Höheres Risiko (gegründete Firmen, Ivens Suche) · 34“**: eigene Seite (`iven_view.render_overview`) mit
    - Kopfzeile „Höheres Risiko · gegründete Firmen · Stand 21.11.2026“ und dem Titel „34 registrierte Firmen. Ivens Suche.“
    - Herkunftszeile „Ivens Firmen-Suche, Regelwerk early-stage.2, Stand 21.11.2026 · Lauf 1684e5a54f024b02 · Stichtag 21.11.2026“
    - Info-Box „Zwei getrennte Rankings … Die Scores sind nicht vergleichbar und werden deshalb nicht gemischt.“ Die Box nennt beide Regelwerke kurz.
    - Filtern nach Branche, Status (Bewertbar / Recherche offen) und Risiko-Label sowie Top 10 / 20 / Alle
    - KPI-Karten: Bewertbar x/y, Ø Screening-Score, Ø Produkt & Technologie, Ø Kunde & Nutzen. Die Karten nutzen das HTGF-Theme, die erste ist dunkel.
    - Ivens Ranking als Tabelle mit den Spalten Rang, Unternehmen, Branchen, Status, Score (Balken), Produkt, Markt, Nachweis, Risiko (Text-Label), Stage, Gründung und Website. Reihenfolge und Werte sind 1:1 übernommen. Ein Klick auf eine Zeile öffnet den Deep Dive.
- **Deep Dive (`?iven=<id>`, teilbarer Link, lädt den Snapshot automatisch):**
  - Kopf: Rang bei Iven, Branchen, Stage, Gründung
  - Chips: Status, Risiko-Label, HTGF-Fit, Datenabdeckung
  - Herkunftszeile
  - bei Ymolution der Hinweis „Auch unter Frühe Vorhaben … nicht vergleichbar“
  - Produktbeschreibung
  - fünf Kennzahlen: Screening-Score mit Obergrenze, die drei Teil-Scores und das Risiko-Label
  - Investmenthypothese (dunkle Box), „Warum jetzt Kontakt?“, „Erste Frage“
  - Tabs:
    - **Scorecard**: Kriterien mit Gewicht, Punkten, Regel und stützenden Fakten
    - **Offene Punkte & Risiko**
    - **Belege & Quellen**: jeder Fakt mit Zitat, Basis und Link sowie alle abgerufenen Quellen und Marktvergleiche
    - **Team**: Karten mit LinkedIn-Pill
  - Kontaktbox:
    - pro Person ein **LinkedIn**-Button (Profil aus Ivens Team-Recherche) oder **„Auf LinkedIn suchen“**
    - Firmenpostfach mit Mailto-Entwurf, Website
    - Dossier-Export als JSON
- **Landing (Snapshot):** zusätzliche Zeile mit dem Hinweis auf die Kategorie „Höheres Risiko“ und die 34 Firmen.
- **Richtung:** Bei Iven ist „Risiko“ ein Text-Label und wird nur als Label angezeigt. Er hat keinen numerischen Risiko-Score, also wird keiner erfunden. Produkt- und Markt-Score gelten wie bei uns: höher ist besser. Offene Werte erscheinen als „offen“ und nie als 0.

## 4. Daten und Snapshot

- `demo_snapshot/iven_adapter.py` erzeugt `demo_snapshot/iven_companies.json` (213 KB, 34 Firmen) aus `data/mvp/jury-reference.json`. Die Werte werden kopiert, nicht neu berechnet. Die Texte kommen aus `mvp.briefs.brief_for(live=True)` und sind damit identisch zur Longlist. Der Test vergleicht alle 34 Zeilen.
- `python -m demo_snapshot.build_snapshot` baut beide Datensätze. Persönliche E-Mails redigiert weiterhin `redact_personal_emails`: drei Adressen in Fakten/Zitaten, nämlich `i@…`, `partner@…` und `imprint@…`. Generische Firmenpostfächer (`info@`, `contact@`, `kontakt@`, `hello@`) bleiben. Die angezeigten Longlist-Texte sind davon nicht betroffen.
- Ladezeit beider Datensätze zusammen deutlich unter 3 s (Test `test_both_datasets_load_fast`).

## Start

```bash
# Unser Dashboard (Snapshot, ohne Netz) -> "Analyse starten" -> Radar -> Kategorie umschalten
.venv/bin/python -m streamlit run app.py
#   Direktlinks: /?view=snapshot   /?iven=company-acb1c3cd21aa0fcaa3a0 (REFACTUM)   /?startup=foekat-03efmv0034 (Ymolution)

# Ivens eigenes Cockpit (mvp, Standard von cockpit.py); FOUNDERRADAR_UI=classic = altes Cockpit
.venv/bin/python -m streamlit run cockpit.py
.venv/bin/python launch_founderradar.py          # Ivens Ein-Klick-Launcher (Port 8502-8519, öffnet Browser)
.venv/bin/python -m mvp.engine --mode replay --as-of 2026-11-21   # Ivens Score-Neuberechnung (schreibt data/mvp/latest.json)

# Snapshots neu bauen / Reproduktion prüfen
.venv/bin/python -m demo_snapshot.build_snapshot
.venv/bin/python AGENT_TEAM/eval/check_iven_reproduction.py
```

Neue Abhängigkeiten: `requests`, `beautifulsoup4` (stehen in requirements.txt; im venv installiert).

## Offene Punkte

- **Gemeinsame `.venv`:** Die venv ist ein Symlink auf `/Users/finnlipek/code/PromptFiction-/.venv`, `bs4` ist dort jetzt installiert. Der laufende 8501-Server merkt davon nichts.
- **`launch_founderradar.py`** wurde nicht ausgeführt, weil er einen Browser öffnet und Port 8502+ belegt. Stattdessen lief der gleiche `streamlit run cockpit.py` mit `FOUNDERRADAR_UI=mvp` als Smoke auf 8599.
- **Ivens `to_dossier`-Änderung** (Quelle der Beschreibung = Selbstbeschreibungs-Signal) ist nicht übernommen, der zugehörige Test ist geskippt. Übernahme erst nach einem Backtest unserer 52 Scores.
- **Discovery-Quelle `combined`:** Ivens Standard wäre `combined`, bei uns bleibt `foekat` Standard. Wer seinen Bestandsweg live will: `FOUNDERRADAR_SOURCING=combined`.
- **Doppelte Firmen:** Ymolution steht in beiden Kategorien, bei Iven mit „Recherche offen“, bei uns als Best Find. Das wird angezeigt und nicht zusammengeführt.
- **KI-Insights** (Ivens Live-KI) sind nicht im Repo gespeichert. Erzeugt Iven welche, würden `Ergebnisse/` und der Adapter-Text abweichen. Dann `python -m mvp.export_jury Ergebnisse` und `build_snapshot` erneut ausführen.
- Keine Screenshots, weil Playwright fehlt.
