# FounderRadar 2.0 - Investment Cockpit

## Run the demo

Python 3.11+ (developed with 3.12). From the project folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m streamlit run app.py     # works offline
```

Then open http://localhost:8501. Direct links for the jury demo:

- `http://localhost:8501/?view=snapshot` opens the snapshot dashboard right away (52 real EXIST leads, as of 21.11.2026).
- `http://localhost:8501/?startup=foekat-03efmv0034` opens the deep dive of the best find (Ymolution).

On the start page pick a **Data source** and press **Start analysis**: **Snapshot (real leads)** (default, offline),
**Demo fixtures (fictional)** or **Live pipeline (online)**. Inside **Radar** a switch toggles between
**Spin-off Radar · pre-founding (EXIST)** and **Company Radar · young GmbH/UG (higher risk)**; the two are ranked
separately. Click any table row for the deep dive; **Back to overview** keeps filters, **New analysis** resets.
Tests: `.venv/bin/python -m pytest -q` (no network needed). The rest of this README is in German.

## Abgabe und Demo

- [Start- und Testanleitung](START-UND-TESTANLEITUNG.md) für Start, Score-Neuberechnung und echten KI-Test.
- [Pitch-Tutorial](PITCH-TUTORIAL.md) für die Vorführung auf dem eigenen Rechner.
- [Ergebnisse](Ergebnisse/ERGEBNISSE.html) nach dem Klonen lokal im Browser öffnen.

## Bedienbares Early-Stage-MVP (2026-11-21)

**Windows:** ZIP vollständig entpacken und `Start-FounderRadar.cmd` doppelklicken.
Python 3.11+ wird benötigt; die getesteten Pakete werden beim ersten Start installiert.
Alternativ: `python -m streamlit run cockpit.py`.

Das Suchprofil umfasst Deutschland und die letzten 24 Monate. **Live-Recherche starten**
ruft öffentliche Webseiten ab und löst Projektspuren zu Firmen auf.
**Score jetzt berechnen** berechnet die Scorecard aus dem gespeicherten Quellenstand.

Scorecard: Produkt/Technologie 40 %, Kunde/Nutzen 35 %, Entwicklungsnachweis 25 %.
Fehlende Werte bleiben offen. Die Rangfolge verwendet die belegte Untergrenze;
die Obergrenze zeigt den offenen Anteil. Sechs Screening-Merkmale bestimmen die
separate Datenabdeckung. Diese ist keine Genauigkeit oder Erfolgswahrscheinlichkeit.
Kapitalbedarf, Finanzierungsphase, IP-Rechte und Differenzierung bleiben Prüfaufgaben.

Die neue Oberfläche ist Standard. `FOUNDERRADAR_UI=classic` öffnet den Bestandsweg,
den die nachfolgenden älteren Abschnitte beschreiben. Dessen 50-Punkte-Defaults
werden im MVP nicht verwendet. `FOUNDERRADAR_ANALYSIS_DIR` steuert nur den Bestandsweg.

Integration: `mvp.engine.run(RunOptions(...), progress)` orchestriert die Schritte.
Ergebnisse: `data/mvp/latest.json`, Historie: `data/mvp/runs/`. Zusätzlich entstehen
fünf bestehende `AnalysisRun`-Verträge unter `data/mvp/analysis/`. `evaluation_v2`
enthält Kriterien, Regelversion, Score-Obergrenze und Projektzuordnung. Die neue
Datenabdeckung wird nicht in das alte `confidence_score`-Feld umgedeutet.
Notizen, Shortlists und Aufgaben nutzen weiterhin `analyst_store.py` und SQLite.
Kein KI-Modell, kein API-Key, keine fiktiven Firmen im neuen Standardablauf.

Grenzen: Kein vollständiger automatischer Handelsregister-Neuzugang. Pro Lauf wird
ein begrenztes Projektbudget bearbeitet, der Rest bleibt im Protokoll. Firmenimpressum,
Projektbezug und Alter werden getrennt geprüft. Namensgleichheit oder Förderbeginn
allein reichen nicht. Quellenfehler und offene Fälle bleiben sichtbar.

## Kombinierte Suche und Investment-Cockpit (Bestandsweg)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run cockpit.py
```

Das Cockpit startet mit der Branchenauswahl. **Start analysis** führt automatisch
Sourcing → Context → Evaluation aus und öffnet die Ergebnisse. Es gibt keinen
manuellen Import. Standardmäßig läuft die vorhandene Demo-Pipeline mit 30 fiktiven
Firmen pro Branche. Die zehn Scoring-Beispiele bleiben Adapter-/Regressionstests.
`main` mit Kontext-Recherche und `feature/scoring` sind integriert.
Die ursprüngliche Anwendung bleibt mit `streamlit run app.py` als Fallback erhalten.

- **Overview:** priorisierte Review-Liste, Qualität/Confidence-Streudiagramm,
  Entwicklungsphasen und nächste Aktionen in einem kompakten Raster. Links stehen
  Pipeline und Research-Abdeckung, mittig die Prüfliste, rechts Firmenfokus und
  nächste Aktion. Darunter folgt die breite Analysefläche. Warme helle Flächen,
  schwarze Schrift und Akzente in Pfirsich, Rosé, Hellgelb und Cyan.
- **Dealflow:** Suche und Filter; eigene Ansichten für Pending Review, Watchlist,
  Entscheidungen und ausgeschlossene Leads; direkter Profileinstieg und JSON-Export.
- **Company Deep Dive:** Investment brief, Company & team, Market & competition,
  Capital & fit, Evidence & activity. Untertabs trennen Produkt, Team, Traction,
  Marktgröße, Wettbewerb, Fund Fit, Finanzierung, Quellen und Aktivitätshistorie.
- **Activities:** Aufgaben mit Owner, Termin, Open/Done und manuellem Kontaktstatus;
  überfällige Aufgaben, abgeschlossene Schritte und gespeicherte Änderungen.
- **Kontakt:** vorbereiteter `mailto:`-Entwurf bei gültiger Adresse, sonst Website.
  Öffnen ist kein Versand und ändert den Kontaktstatus nicht.
- **Szenarien:** Ownership-/Exit-Rechner und Deep-Tech-Readiness-Workspace mit
  ausdrücklich gekennzeichneten Analystenannahmen.

Die automatische Übergabe verwendet `AnalysisRun` aus `pipeline.run_pipeline`.
Für Live-Betrieb und einen optionalen lokalen Extraktor:

```powershell
$env:FOUNDERRADAR_MODE = 'live'
$env:FOUNDERRADAR_SCREENING_REPORT = 'climate.json'
$env:FOUNDERRADAR_OLLAMA_MODEL = 'dein-installiertes-modell'
$env:FOUNDERRADAR_DB = 'C:\Pfad\screening.sqlite3'
.\.venv\Scripts\python.exe -m streamlit run cockpit.py
```

Das Live-Sourcing übernimmt bestätigte Leads und Feldbelege aus dem konfigurierten
Screening-Export. Die Branche muss zur Auswahl im Cockpit passen. Ollama ist optional.
Details und konkrete
Integrationslücken: [Cockpit-Daten und Integrationen](docs/COCKPIT.md).

Ohne DB-Variable: `data/screening.sqlite3` (Git-ignored). Additive Migrationen erhalten
bestehende Entscheidungen. Demo und Live bleiben getrennt. Jede Änderung speichert
einen Snapshot in derselben Transaktion. **Plan next step** speichert eine Aufgabe
auch ohne Investmententscheidung; diese bleibt dann Pending Review. Pro Firma wird
eine aktuelle Folgeaufgabe verwaltet, frühere Stände bleiben in der Historie.
Analyseläufe leben in der Browsersitzung; Entscheidungen und Aufgaben überleben
Neustarts. SQLite ist für den Hackathon gedacht, ohne Mehrbenutzer-Login.

### Architektur und Grenzen

| Datei | Aufgabe |
| --- | --- |
| `cockpit.py` | Branchenauswahl, Navigation, Overview, Dealflow, Activities |
| `cockpit_details.py` | Firmenprofil, Untertabs, Entscheidungen und Aufgaben |
| `cockpit_service.py` | Automatische Pipeline-Übergabe, optional Ollama, Mailto |
| `cockpit_style.py` / `cockpit_visuals.py` | Kompaktes Layout und datenbasierte Charts |
| `cockpit_data.py` | Normalisiertes Lead-Modell, Legacy/v2-Adapter, HTGF-Heuristik, Szenariomathematik |
| `cockpit_research.py` | Marktcharts, Competition, Funding, sektorbezogene Ansichten |
| `cockpit_context.py` / `cockpit_research_v2.py` | Strukturierte Recherche, Claims und Quellen, datentreue Zeitreihen und Marktmodelle |
| `config/htgf.v1.json` | Versionierte Kriterien mit Quelle, Prüfdatum und Mandatsabgrenzung |
| `analyst_store.py` | SQLite; Aufgaben, Kontaktstatus und transaktionale Änderungshistorie |
| `tests/test_cockpit.py` / `tests/test_workspace.py` | Scoring-Fixtures, Adapter, Charts, Mathematik, Navigation und Persistenz |

Der bestehende Python-/Streamlit-Stack wird weiterverwendet. Ein separater
React-/Next.js-Build und eine HTTP-API sind für diese Implementierung nicht nötig.
Die Engines werden nicht neu implementiert. Die Integration der Team-Branches erhält
beide Modell-Feldmengen und erlaubt das belegte Ergänzen eines zuvor unbekannten
first_signal_date; vorhandene Sourcing-Daten bleiben geschützt.

`context_v2` und `evaluation_v2` sind optionale Erweiterungsobjekte. Kanonische Felder
können darin ergänzt werden; das Original bleibt in Lead.raw erhalten. Doppelte IDs
werden zurückgewiesen. Legacy-Confidence 0-1 wird als Prozent angezeigt; native
confidence_score 0-100 entsprechend normalisiert. Vollständig unbelegte Dimensionen
werden als **Not assessed** dargestellt. Gemischte Scores bleiben Originalwerte und
tragen einen Hinweis auf neutrale 50-Punkte-Anteile. Risiko: 100 = hohes Risiko,
entsprechend `scoring/SCORING.md`. Fehlende DB-Angaben bleiben unbekannt, Proxy-Gründung
bleibt Proxy, first_signal_date wird nicht als Engine-Entdeckung ausgegeben.
Dummy-Namen und example-Domains kennzeichnen Demo-Daten.
Die native Evaluation erhält ihren vollständigen Scoring-Output in `evaluation_v2`;
der Adapter kombiniert dessen Evidence mit den Context-Belegen. Ausschlüsse verhindern
eine ungeprüfte Potential-Fit-Anzeige und die Aufnahme in die priorisierte Review Queue.

Die [offiziellen HTGF-Kriterien](https://www.htgf.de/) wurden am 20.11.2026 geprüft:
frühe Phase, Technologiefokus, höchstens drei Jahre und deutscher Sitz/Betriebsstätte.
800.000+ EUR sind ein flexibler Sweet Spot, keine harte Ausschlussgrenze.
Potential Fit benötigt passende vier Kernkriterien; Ticket und Portfolio-Overlap
bleiben gesonderte Prüfungen. Geografie wird nicht aus Domain/Sprache abgeleitet.
Deshalb bleiben gute Scoring-Dummies ohne geografische Angaben Review Required.
Die Heuristik gilt für Erstinvestitionen und ist keine offizielle HTGF-Bewertung.

### Research-Vertrag

Der native Vertrag in `research_models.py` umfasst unter `context_v2` Unternehmen,
Gründer, Produkt, Traction, Finanzierung und `market_intelligence`. Claims behalten
ihre Evidence-IDs und ihren Ursprung; numerische Marktangaben zusätzlich Einheit,
Währung, Region, Zeitraum, Methodik und Datentyp. Das Cockpit zeigt die Angaben
in den jeweiligen Untertabs mit Quellenlinks. Vorhandene flache Felder bleiben
erhalten; unbekannte Werte werden nicht mit null aufgefüllt.

Im Demo-Bestand gibt es **150 Unternehmen in fünf Branchen**, jeweils 30 pro Lauf.
`industrial-16` enthält zusätzlich ein Marktdossier: Eurostat-Unternehmensbestand
2021–2023, ein daraus berechnetes TAM/SAM/SOM-Szenario, drei Wettbewerber und eine
Vergleichsfinanzierung. Das Unternehmen selbst bleibt fiktiv. Modellannahmen und
öffentliche Referenzquellen werden getrennt gekennzeichnet; eine Finanzierungsrunde
ist keine Unternehmensbewertung und eine Unternehmensanzahl keine Umsatzzeitreihe.

Die Oberfläche verwendet auch die bereits vorhandenen operativen Felder: Umsatz,
Kundenzahl, Teamgröße, Finanzierungsvolumen und -phase, Produktstatus, Traction-Notizen,
Gründerprofile, Discovery-Signale und ausführliche Bewertungsbegründungen.

Zusätzlich unterstützte Legacy-Felder auf Lead-Ebene oder in flachem `context_v2`:

- `market_intelligence`: definition, geography, year, methodology, sizing,
  growth_series, drivers, uncertainties, growth, maturity, competition_intensity,
  commercialization_potential.
- `sizing`: Einträge mit label (TAM/SAM/SOM), value, unit, source. Grafik nur bei
  drei belegten Größen, gleicher Einheit, TAM >= SAM >= SOM und vollständiger Methodik.
- `growth_series`: year, value, unit, definition, geography, as_of, source,
  kind (Historical/Forecast). Mindestens zwei eindeutige Jahre mit identischer
  Einheit, Marktdefinition, Geografie und Datenstand. Forecasts gestrichelt;
  CAGR aus Endpunkten, inklusive Prognosen, wenn vorhanden.
- `competitors`: Strings oder Objekte mit name, product, customer_segment,
  geography, stage, differentiation, funding, source.
- `competitive_positioning`: x_label, y_label, rationale, points mit name, x, y,
  source. Ohne belegte Koordinaten und begründete Achsen keine Positionierungsgrafik.
- `comparable_transactions`: name, type, date, value, currency, value_type,
  revenue, ebitda, multiple_basis, metrics_comparable, source. Multiples nur bei
  Enterprise Value, positivem Nenner, EV/Revenue oder EV/EBITDA und explizit
  vergleichbarer Währung/Periode (metrics_comparable: true).
- `sector_research`: z. B. arr, retention, unit_economics für Digital Tech;
  technology_readiness, commercial_pilots, capital_intensity für DeepTech;
  regulatory_pathway, patent_protection, next_catalyst für Life Sciences/Chemistry.

Noch kein dedizierter Market-Research-Endpunkt: kein vorgetäuschter Generate-Button.
Die Kontext-CLI unterstützt gezielte Marktrecherche über `--lead`, `--market-input`
und `--market-source` (siehe unten). Das Cockpit zeigt deren strukturierten Output
automatisch. Außerhalb des genannten Demo-Marktdossiers fehlen überwiegend
quantitative Marktdaten; diese Lücken werden nicht mit erfundenen Zahlen gefüllt.

Prüfung:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q cockpit.py cockpit_data.py cockpit_research.py
```

## Bisherige Anwendung und Pipeline

FounderRadar sucht frühe Deep-Tech-Gründungsvorhaben in Deutschland und bewertet sie für ein VC-Screening.
Vier Module laufen nacheinander: Sourcing aus dem Förderkatalog des Bundes, Kontext aus öffentlichen Quellen,
regelbasiertes Scoring und ein Streamlit-Dashboard mit Ranking und Deep Dive. Jede Angabe trägt ihre Quell-URL;
was keine Quelle hat, bleibt leer und wird nicht geschätzt.

## Schnellstart

Python 3.11 oder neuer (entwickelt mit 3.12). Im Projektordner:

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m streamlit run app.py
```

Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Danach http://localhost:8501 öffnen. Die Tests laufen ohne Netz. Nach Änderungen an `.streamlit/config.toml`
den Server mit Strg+C beenden und neu starten. Die folgenden Befehle setzen eine aktivierte venv voraus
(`source .venv/bin/activate` bzw. `.\.venv\Scripts\Activate.ps1`), dann genügt `python`.

### Running the demo app (Demo-App)

Start (works offline): `.venv/bin/python -m streamlit run app.py`, then open http://localhost:8501.
Direct links for the demo: `http://localhost:8501/?view=snapshot` opens the snapshot dashboard immediately,
`http://localhost:8501/?startup=foekat-03efmv0034` the deep dive of the best find (Ymolution).

1. On the start page choose the **Data source** and press **Start analysis**:
   - **Snapshot (real leads)**, default: frozen real run over 52 funding-catalogue leads with context
     (website, imprint, OpenAlex, idw, Wayback, database search) and scoring, as of 21.11.2026. Loads in under
     a second from `demo_snapshot/` and needs no network.
   - **Demo fixtures (fictional)**: 30 invented startups per category.
   - **Live pipeline (online)**: up to 10 real leads per category, about 10–15 s per lead.
2. The dashboard shows filters (industry, stage, "Only without DB profile", top 10/20/50) and KPI cards; in snapshot
   and live mode also earliness (backtest headline 11/11, median 21 months, n=11 hand-picked; share without DB
   profile; months of lead time) and, in the snapshot, the **Best Find** with signal timeline and sources. Plus the
   3D potential space, stage distribution, comparison of the top ten, the ranking table (score, stage, industry,
   website, founders, first signal, DB check, lead time), the "Noise and rejected" section and the JSON export.
   The **Company Radar · young GmbH/UG (higher risk)** category shows registered young companies with their own
   rule set and a separate ranking (`?iven=<id>` opens one).
3. A table row, "Meet the startup" or "Open deep dive" opens the deep dive: scores, earliness chips, signal
   timeline with source URLs, team card (person, role, background, publications), investment thesis, risks,
   evidence and contact. The contact button opens an e-mail draft and sends nothing.
4. **Back to overview** keeps filters and top-N; **New analysis** discards results and the selection.

Rebuild the snapshot (after scoring changes; reads `AGENT_TEAM/reports/scratch/loop1/full_dossiers.json`,
offline): `.venv/bin/python -m demo_snapshot.build_snapshot` (other dossiers with `--dossiers PATH`).
The snapshot contains real imprint and founder names (public business data); the team decides before committing it
to the public repo (see `AGENT_TEAM/reports/final_gate.md`, data protection).

Alle Scores liegen zwischen 0 und 100. Höhere Unternehmens- und Marktwerte sind besser, niedrigeres Risiko ist
besser. KPI-Mittelwerte und Stage-Verteilung beziehen sich auf die sichtbaren Top-N. Fehlende Scores gelten als
unbekannt, nicht als null, und fallen aus Mittelwerten heraus; unvollständige 3D-Punkte bleiben in der Tabelle.

## Die vier Schritte

| Schritt | Modul | Vertrag (Eingabe → Ausgabe) | Befehl |
| --- | --- | --- | --- |
| 1 Sourcing (Person 1) | `sourcing/` | `search(SearchCriteria) → list[RawLead]` | `python -m sourcing foekat --out shortlist.json` |
| 2 Kontext (Person 2) | `context/` | `enrich(RawLead) → EnrichedLead`; CLI: RawLead-Liste → `ContextResult` | `python -m context shortlist.json dossiers.json` |
| 3 Scoring (Person 3) | `evaluation/engine.py`, `scoring/`, `scoring_input.py` | `evaluate(ScoringInput, *, lead=EnrichedLead) → EvaluationScores` | `python -m scoring dossiers.json --out scoring_out` |
| 4 Dashboard (Person 4) | `app.py`, `dashboard.py`, `deep_dive.py`, `charts.py`, `market_view.py`, `ui_theme.py` | `AnalysisRun` / `ResearchResult` → Ansicht | `python -m streamlit run app.py` |

`models.py` ist der gemeinsame Datenvertrag (mit `research_models.py` für `context_v2`/Marktdaten und
`scoring_models.py` für den `ScoringInput`; `scoring_input.py`/`scoring_market.py` bauen ihn, `mock_data.py` hält
drei Mini-Fixtures für Einzelschritt-Tests). `pipeline.run_pipeline(criteria, use_mock=…)` führt die Schritte
1–3 aus und liefert ein `AnalysisRun` (Schema-Version 2.0) mit Suchkriterien, Modus, Zeitstempel, Lead-Zahlen
und `ResearchResult` (`leads` bewertet, `issues` Fehler je Lead). Sourcing filtert nur Branche und belegten
Deutschland-Bezug, dedupliziert nach ID und behält die Fundreihenfolge; Kontext sammelt Fakten ohne Ranking;
erst die Bewertung sortiert nach `overall_score` (fehlende Gesamt-Scores zuletzt), bei Gleichstand nach der
Schritt-1-Priorität, dann nach ID (`pipeline.ranking_key`). Was keine Quelle hat,
geht im Scoring neutral ein, nicht als schlechtester Wert (`scoring/SCORING.md`). Wer welches Modul verantwortet, steht in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Live-Pipeline: von null bis Score

```bash
# 1. Fundliste aus dem Förderkatalog (Netz; danach 14 Tage aus .cache/context.db, ohne Netz)
python -m sourcing foekat --since 2024-01-01 --out shortlist.json --stats stats.json   # alle Leads (Stand 20.11.2026: 733)
python -m sourcing foekat --out top.json --min-priority 80                             # 54 Leads

# 2. Kontext: online für die ersten fünf (Standard) oder nur aus mitgelieferten Signalen
python -m context top.json dossiers.json --limit 5
python -m context top.json dossiers.json --light          # ganze Liste, ohne Netz-Lookups
python -m context top.json dossiers.json --offline        # keine Seiten, keine Lookups

# 3. Scoring: liest das ContextResult direkt und schreibt scores.json, scores.csv, scores.schema.json
python -m scoring dossiers.json --out scoring_out --stichtag 2026-11-20
```

Ohne Netz und Cache lassen sich die Schritte 2 und 3 mit den mitgelieferten Leads prüfen:

```bash
python -m context examples/sourcing/sample_leads.json dossiers.json --offline --limit 8
python -m scoring dossiers.json --out scoring_out
```

In Python liefert `run_pipeline(SearchCriteria(industry=…), use_mock=False)` denselben Ablauf in einem Aufruf.
Weitere Optionen: `python -m sourcing foekat --help`, `python -m context --help`, `python -m scoring --help`.

## Datenvertrag und Dokumentation

| Dokument | Inhalt |
| --- | --- |
| [`sourcing/FOEKAT.md`](sourcing/FOEKAT.md) | Schritt 1: Abruf, Felder, Branchenregeln, Priorität, Grenzen, Datenschutz |
| [`context/ENRICHMENT.md`](context/ENRICHMENT.md) | Schritt 2: Live-Abfragen je Quelle, Felder, Grenzen |
| [`SCORING_HANDOFF.md`](SCORING_HANDOFF.md) | Übergabe 2 → 3: `ScoringInput`, Status, Export und Replay |
| [`scoring/SCORING.md`](scoring/SCORING.md) | Schritt 3: Regeln, Gewichte, Mapping aufs Dashboard-Modell |
| [`examples/README.md`](examples/README.md) | Beispieldateien, Schemas und wie man sie neu erzeugt |
| [`NOTICE.md`](NOTICE.md) | Übernommene Verfahren und Datenquellen |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Setup, Tests, Branches, Verantwortliche |

Maschinenlesbare Schemas: [`examples/analysis-schema.json`](examples/analysis-schema.json) (`AnalysisRun`),
[`examples/context-schema.json`](examples/context-schema.json) (`ContextResult`),
[`examples/scoring-input-schema.json`](examples/scoring-input-schema.json) (`ScoringInput`),
[`examples/market-input-schema.json`](examples/market-input-schema.json) (`MarketIntelligence`).

### Pflichtfelder aus Schritt 1 (`RawLead`)

| Fachliches Feld | Feld | Typ |
| --- | --- | --- |
| Name Gründer | `founders` | Liste von Namen |
| E-Mail | `contact_email` | primäre Kontaktadresse oder null |
| Name Unternehmen | `name` | Text |
| Website | `website` | HTTP(S)-URL oder null |
| Branche | `industry` | Wert aus `Industry` |
| Gründungsjahr / -monat | `founding_year`, `founding_month` | Ganzzahl bzw. 1–12 oder null |
| Standort | `location` | Text oder null |
| VC-Beteiligung laut Sourcing | `has_vc` | true, false oder null |

Dazu `id`, `description`, `country`, `source_name`, `source_url`, `country_evidence`, `is_demo`; optional
`signals`, `htgf_sector`, `prioritization_reason`. Die Quelle bleibt bis ins Dashboard erhalten. Schritt 1
recherchiert nicht tief: fehlende Kontaktangaben bleiben null, eine .de-Domain allein belegt keinen deutschen
Sitz. Die Kontext-Engine übernimmt alle Eingangsfelder mit `EnrichedLead(**lead.model_dump(), …)` und darf
sie nicht verändern.

### Pflichtfelder aus Schritt 3 (`EvaluationScores`)

| Fachliches Feld | Feld | Typ |
| --- | --- | --- |
| Score | `overall_score` | 0–100 oder null |
| Risiko | `risk_score` | 0–100 oder null; höher = riskanter |
| Marktpotenzial | `market_potential_score` | 0–100 oder null |
| Unternehmensscore | `company_score` | 0–100 oder null |
| Stage | `stage_classification` | Pre-Seed / Seed / Early Growth / Unbekannt |
| Value Proposition | `value_proposition` | nicht leerer Text |
| Investmenthypothese | `investment_thesis` | Text |

`quality_score`, `earliness_score`, `confidence_score`, `risks`, `score_drivers` und `open_questions` sind
optional. `funding_stage` ist eine Kontextangabe; `stage_classification` ist die Einordnung aus Schritt 3.

### Zurückgehaltene Leads

Vor der Bewertung hält die Live-Pipeline einen Lead als `issue` zurück, wenn am Stichtag kein nutzbarer
Deutschland-Beleg vorliegt oder der VC-Status `confirmed` bzw. `conflicting` ist. Ein unbekannter VC-Status ist
bei Forschungsprojekten der Normalfall: Solche Leads werden bewertet und tragen die Frage nach Investoren in
`research_questions`. Fehler einzelner Kontext- oder Bewertungsaufrufe stoppen die übrigen Leads nicht; ein
Totalausfall im Sourcing wird in der Oberfläche gemeldet.

## Grenzen und Datenschutz

- EXIST-Teams sind meist noch nicht gegründet: Gründer, E-Mail, Website und Gründungsdatum fehlen in Schritt 1;
  die Hinweise `pre_founding_team` und `internal_review_case` markieren interne Prüffälle.
- Live-Abfragen sind auf feste öffentliche Quellen beschränkt (Förderkatalog, Impressum, OpenAlex, Wayback,
  idw, optional Google Patents); keine offene Websuche, keine kostenpflichtigen Datenbanken. Grenzen je Quelle
  in `context/ENRICHMENT.md`.
- Die Demo-Formel `45 % Unternehmen + 35 % Markt + 20 % (100 − Risiko)` gilt nur im Fixture-Generator
  (`demo_portfolio.py`); die Live-Gewichte stehen in `scoring/scoring_config.yaml`. Das Team muss beide noch
  fachlich abstimmen.
- Die Sitzung liegt im Streamlit Session State; ein Browser-Reload kann sie verwerfen. JSON-Export ist da,
  Import und dauerhafte Speicherung fehlen. `?startup=<ID>` funktioniert nur innerhalb eines Analyselaufs.
- Datenschutz: Schritt 1 entfernt Namen mit akademischem Titel und untitelte AG-Leitungen aus Katalogtexten; die Katalogabfrage in Schritt 2
  übernimmt die Ausführende Stelle ungefiltert, Cache (`.cache/context.db`) und `--raw-dir` enthalten
  unveränderte Zeilen. E-Mails werden nur als generische Impressumspostfächer übernommen (`imprint_email`).
  Rechtsgrundlage und Löschfrist sind offen; Details in `sourcing/FOEKAT.md`. Der Förderkatalog nennt keine
  Nutzungsbedingungen; vor einer Weitergabe außerhalb des Hackathons beim Betreiber nachfragen.

## Lizenz und Namensnennung

Für das Repository ist **noch keine Lizenz festgelegt**; ohne `LICENSE` gilt das Urheberrecht der Autor:innen.
Die Verantwortlichen müssen eine Lizenz wählen. Übernommene Verfahren (udb-foerderkatalog-scraper, MIT;
startup-valuation, MIT) und Datenquellen stehen in [`NOTICE.md`](NOTICE.md).

## Design-Notizen

Notizen der Modulverantwortlichen, die über den Vertrag hinausgehen.

### Schritt 1: Sourcing aus dem Förderkatalog

`sourcing.engine.search(criteria)` liefert EXIST-Projekte aus dem
[Förderkatalog des Bundes](https://foerderportal.bund.de/foekat/): EXIST-Forschungstransfer (FKZ `03EF*`) und
EXIST-Gründungsstipendium (`03EG*`) mit Projektbeginn ab 01.01.2024 (`--since` oder `FOEKAT_SINCE`), laufend
und abgeschlossen. Code: `sourcing/foekat_export.py` (Abruf, Trefferzahl-Prüfung, Bereinigung, Anfragebudget
60), `sourcing/mapping.py` (Zeilen → RawLead, Branche, Priorität), `sourcing/engine.py`. Je Programm laufen
eine Detailsuche und der CSV-Export; fehlen FKZ, wird nach FKZ-Präfix aufgeteilt. Exit-Code 1 = unvollständig,
2 = Abbruch. Stand 20.11.2026: 733 Leads (146 × 03EF, 587 × 03EG), siehe `examples/sourcing/shortlist.json`.
Mit gefülltem Cache (14 Tage) sind Folgeläufe byte-identisch und ohne Netz.

Pro Projekt entsteht ein Lead mit einem beschrifteten Katalogsignal je FKZ (Schritt 2 macht daraus offline
einen `Grant`) und der Katalog-Detailseite als Deutschland-Beleg. Die Branche kommt aus Schlüsselwortregeln auf
ganzen Token, Grundlage Thema (83), nur Institut (302) oder Programmstandard (348, `htgf_sector=null`, Hinweis
`industry_unclassified`). Jeder Lead hat eine Priorität 0–100; die CLI sortiert danach. `search(criteria)`
liefert Thema- vor Institut-Leads und Standard-Leads nur mit `include_unclassified=True`.

### Schritt 2: Kontext

Die CLI-Eingabe ist ein priorisiertes JSON-Array von RawLeads mit Deutschland-Beleg; `--lead ID` wählt einen
Lead. Standardmäßig werden die ersten fünf Leads vertieft, `--light` verarbeitet die ganze Liste anhand der
mitgelieferten Signale. Die Ausgabe ist ein `ContextResult` (Dossiers in `leads`, Fehler in `issues`);
`collect_context(leads, use_mock=False)` liefert denselben Vertrag in Python. `htgf_sector` nutzt die fünf
Track-Kategorien, `industry` bleibt die Produktkategorie.

Ein Signal enthält `source`, `type`, `url`, `date` (ISO-Datum oder null) und `evidence` (Quelltextauszug).
Online liest Schritt 2 zusätzlich die Startseite, bis zu vier verlinkte Unternehmensseiten und die ursprüngliche
Fundseite, falls daraus noch kein Auszug mitgeliefert wurde. Der Extraktor erkennt eindeutige deutsch- und
englischsprachige Angaben wie „Produktreife: MVP“, „Zielkunden: Industriebetriebe“
oder „Kim Muster – Rolle: CTO“; bei freier Web-Sprache ist die Abdeckung begrenzt. `--ollama-model` (z. B.
`qwen3.5:4b`) lässt ein lokales Modell noch leere Textfelder mit wörtlichen Zitaten füllen; Python prüft die
Zitate gegen die Quellenausschnitte, bei Modellfehlern bleiben die Regelwerte.

Dossierfelder: `founder_profiles` (Name, Rolle, Qualifikation), `target_customers`, `customer_problem`, `solution`, `product_stage`,
`funding_status`, `vc_status`, `first_signal_date`. Belege verknüpfen Aussagen mit Feldern und enthalten
Quell-URL, Abrufdatum und ggf. Publikationsdatum. Bei widersprüchlichen Angaben bleiben die Werte leer und die
konkurrierenden Belege erhalten. `vc_status` bleibt ohne ausdrückliche Angabe `unknown`; ein positives
VC-Signal gegen die Sourcing-Angabe ergibt `conflicting`. `funding_status` erfasst auch Eigenfinanzierung,
Förderung und Finanzierung unbekannter Art; Bundesförderung ohne VC-Signal ergibt `non_vc_funded`. Für
Scorecard und VC-Methode enthält das Dossier außerdem Markt, Technologie, Wettbewerb, Vertrieb, weiteren
Kapitalbedarf, Rundengröße und Pre-Money-Forderung; offene Punkte stehen als Fragen fürs Erstgespräch in
`research_questions`. Ältere Exporte lassen sich weiterhin validieren.

Live-Abfragen (ohne `--offline`/`--no-lookups`), jedes Ergebnis mit eigener Quell-URL:

| Quelle | Modul | Felder |
| --- | --- | --- |
| Impressum der Website | `context/imprint.py` | `imprint_url`, `legal_form`, `in_formation`, `managing_directors`, `register_id`, `imprint_email` |
| Förderkatalog des Bundes | `context/foekat.py` | `grants` (Programm, FKZ, Summe, Laufzeit), `match_confidence` |
| OpenAlex | `context/openalex.py` | je Gründer `institution`, `openalex_url`, `works_total`, `works_in_field`, `match_confidence` |
| Wayback CDX | `context/wayback.py` | `first_web_capture`, `in_databases`, `first_db_date`, `database_urls` |
| idw-online | `context/idw.py` | datierte Pressemeldungen als Signale, `founding_year_hint` |
| Texte (Regeln, optional Ollama) | `context/classify.py` | `product_stage`, `product_type`, `regulated_market`, `ip_status`/`patents`, `partners`, `business_model`, `market_size_eur`, `competitors` |
| Google Patents (nur mit `--patents`) | `context/patents.py` | `patents`, `ip_status` |

Alle Abrufe und Modellantworten laufen durch `.cache/context.db` (`--cache off` schaltet ihn ab); bei
Modell-Timeouts kann ein Zitatfeld im zweiten Lauf trotzdem fehlen. `enrichment_sources` und
`enrichment_errors` zeigen je Lead, welche Abfragen liefen.

**Strukturierte Dossiers (`context_v2`)** ergänzen `company`, `founders`, `product`, `traction`, `funding`,
`discovery_signals`, `market_intelligence`, `research_status` und `updated_at`. Aussagen referenzieren Belege
über `evidence_ids`. `source_matched` heißt, der Extraktor hat die Aussage im Ausschnitt gefunden;
`source_reviewed` kennzeichnet begutachtete Quellen, `assumption` Annahmen, `unverified` ungeprüfte Angaben.
`origin` unterscheidet Quellenaussage, Modellzitat und Interpretation. Traction trennt zahlende Kunden, Kunden
mit offenem Zahlstatus, bezahlte und unbezahlte Piloten, LOIs, kommerzielle und Forschungspartner; ein
Förderantrag ändert den VC-Status nicht.

**Gezielte Marktrecherche:**

```bash
python -m context shortlist.json dossier.json --lead <ID> --market-input marktquellen.json
python -m context shortlist.json dossier.json --lead <ID> --market-source <URL>
```

`--market-input` erwartet ein Objekt gemäß `examples/market-input-schema.json`; `--market-source` liest bis zu
sechs öffentliche HTML-Seiten (Cache bis 64 Seiten in 15-Minuten-Fenstern). Beides ist kombinierbar. Für
Bottom-up-Rechnungen enthält `sizing_inputs` `addressable_companies`, `annual_revenue_per_company`,
`serviceable_share` (0–1) und `delivery_capacity`; alle Werte eines Szenarios nutzen dieselbe Geografie und
Periode, der SOM die kleinere Zahl aus Kapazität und SAM. Zeitreihen trennen beobachtete Werte von Prognosen;
CAGR setzt vergleichbare Jahreswerte voraus; Transaktionsmultiples brauchen einen veröffentlichten Enterprise
Value und eine positive, vergleichbare Jahreskennzahl. Die HTGF-Matrix erhält TRL und eine begründete
Marktsicherheit, wenn beide strukturiert und mit Belegen vorliegen. Im Deep Dive von `industrial-16` zeigt der Tab
**Marktrecherche** die Eurostat-Reihe zur Unternehmensbasis, ein TAM-/SAM-/SOM-Szenario, drei Wettbewerber und
eine veröffentlichte HTGF-Referenzrunde. Die Grundgesamtheit ist eine Obergrenze, Preis und Reichweite sind
Annahmen; eine belastbare Marktumsatzreihe und eine Prognose fehlen für dieses Beispiel noch.

### Scorecard und VC-Methode

```bash
python -m evaluation.valuation dossiers.json assumptions.json valuations.json
```

`assumptions.json` ordnet jeder Lead-ID Methodenannahmen zu. `scorecard`: `benchmark_pre_money_eur`,
`benchmark_source` und sechs `factors` (`team`, `market`, `technology`, `competition`, `sales`,
`capital_need`) mit `weight` (Summe 1), `relative_score` (1 = Benchmark) und `rationale`. `vc_method`:
`exit_equity_value_eur`, `future_dilution` (0–1) und `target_moic`; der maximale Einstiegspreis vor der Runde
ist der verwässerungsbereinigte Exit-Eigenkapitalwert geteilt durch den Ziel-MOIC abzüglich der Rundengröße.
Die Ausgabe zeigt auch den Abstand zur Preisforderung. Beide Methoden rechnen nur bei belegtem VC-Status
`reported_none`; sonst bleiben alle Euro-Felder leer (bei EXIST-Leads der Normalfall). Fehlen Rundengröße
oder Preisforderung, bleibt der VC-Block offen. Euro-Ergebnisse sind Dezimalstrings; der Rechenkern ist
lokal, ohne externen Dienst.

### Demo und Live-Integration

`demo_portfolio.py` enthält deterministische Fixtures und die Adapter `demo_search`, `demo_enrich`,
`demo_evaluate`, die je nur die Felder ihres Schritts liefern und dieselben Pipeline-Funktionen durchlaufen wie
der Live-Pfad. Im Bereich Industrial / DeepTech enthält `industrial-16` echte öffentliche Marktquellen.
Provider, Enricher und Evaluator lassen sich für Tests einzeln injizieren. Beispiel eines exportierten
Demo-Laufs: `examples/analysis-demo.json`.

### Investment-Cockpit, Screening und Analystenentscheidungen (Iven, Leonard)

Das Dashboard hat drei Ansichten (Umschalter oben): **Radar** (Standard: Scores, Earliness, Best Find, Ranking),
**Screening & Entscheidungen** (`screening.py`: Fund Fit, Analystenstatus, Suche und Filter) und
**Investment-Cockpit** (`cockpit.py`: Überblick, Dealflow, Firmenbrief, Aktivitäten; Details `docs/COCKPIT.md`).
Der Deep Dive hat den Tab „Investment-Briefing & Entscheidung“ mit Scorecard (`scorecard.py`), Stärken/Risiken und
dem Entscheidungsformular. Entscheidungen und Aktivitäten speichert `analyst_store.py` lokal in SQLite
(`data/screening.sqlite3`, per `FOUNDERRADAR_DB` umstellbar; Demo und echte Leads getrennt). Das Cockpit läuft auch
eigenständig: `python -m streamlit run cockpit.py`.

Sourcing aus einem Screening-Export statt aus dem Förderkatalog:

```bash
FOUNDERRADAR_SCREENING_REPORT=climate.json FOUNDERRADAR_MODE=live .venv/bin/python -m streamlit run app.py
.venv/bin/python -m context climate.json dossiers.json --light --offline --scoring-output scoring.json
```

### Dashboard

`app.py` (Kategorienwahl, Analyseauftrag, keine Bewertungslogik), `ui_theme.py` / `.streamlit/config.toml`
(Layout, Farben, Typografie), `dashboard.py` / `charts.py` (Visualisierungen, Ranking), `deep_dive.py`
(Dossier und Kontakt), `market_view.py` (Marktrecherche). Visuelle Referenz: die vom Team bereitgestellte
HTGF-Ansicht mit großer Typografie, Weißraum, klaren Kennzahlen und dezenten Akzenten; FounderRadar verwendet
eine eigene Marke (Farben und Schriften: `ui_theme.py`, Herkunft in `NOTICE.md`). Technik: [Streamlit](https://docs.streamlit.io/develop/api-reference/data/st.dataframe),
[Plotly](https://plotly.com/python/3d-scatter-plots/).

## Investment Screening Cockpit: erweiterter Vertrag

Die bestehenden v2-Verträge wurden um optionale Screening-Felder erweitert.
Alte JSON-Dateien bleiben lesbar; fehlende Felder werden als Unknown/null dargestellt.

- Schritt 1: discovery_source, first_signal_date, discovered_at, initial_signal.
  source_url verweist auf den Originalfund; source_name bleibt als Legacy-Feld erhalten.
- Schritt 2: founder_profiles mit Rollen, Hintergründen, Erfahrungen und Belegen;
  Problem, Zielkunden, Produktmechanik/-reife, Geschäftsmodell, Markt, Wettbewerber,
  Technologie/IP und Differenzierung. traction_evidence und funding_events halten
  belegbare Ereignisse fest. Evidence.published_on ergänzt das Abrufdatum.
- Funding-Status: Bootstrapped / Grant-funded / Pre-Seed / Seed / Later / Unknown.
  Keine gefundenen Finanzierungsinformationen bedeuten Unknown, niemals Bootstrapped.
- Schritt 3: fund_fit_score, team_score, bestehender earliness_score, getrennte
  hard_exclusions, eligibility_status und Begründungen für die drei Scores.
  Ein expliziter Ausschluss übersteuert den Screening-Status.

Die neuen Scores werden noch nicht automatisch berechnet: konkrete Fondskriterien,
Gewichte und die vollständige Earliness-Definition stehen aus. Demo-Earliness-Werte
sind ausdrücklich fiktive Altwerte; Fund Fit und Team bleiben ohne Grundlage null.
Die Anforderungen endeten mitten in der Earliness-Definition; weitere Evaluation-
und Designvorgaben müssen noch ergänzt werden.

Die Startup Overview unterstützt alle Leads, Top 10/20, Funding-Filter und das
Ausblenden expliziter Ausschlüsse. Der Company Deep Dive zeigt die neuen Fakten
und die Discovery Timeline. Es ist weiterhin eine Demo, keine Live-Recherche.
