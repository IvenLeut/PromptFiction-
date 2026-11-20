# FounderRadar

Ein zusammenhängender Ablauf für VC-Screening: **Kategorie auswählen → Analyse
starten → visualisierte Ergebnisse → Startup-Deep-Dive**.

Die aktuelle Version arbeitet vollständig mit fiktiven Daten. Pro Kategorie stehen
30 Demo-Startups zur Verfügung. Keine echten Kontakte, Registerfunde oder Investmentempfehlungen.

## Start

Python 3.11 oder neuer. Im Projektordner:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

http://localhost:8501 öffnen. Bei einem laufenden Server nach Änderungen an
`.streamlit/config.toml` den Server mit Strg+C beenden und neu starten.
Tests: `.\.venv\Scripts\python.exe -m pytest -q`

## Bedienung und Visualisierungen

1. Kategorie auf der Startseite auswählen und **Analyse starten** drücken.
2. Sourcing, Kontextsammlung und Bewertung laufen automatisch nacheinander.
3. Das Dashboard zeigt Top 10 oder Top 20 der gewählten Kategorie:
   - vier KPI-Anzeigen: durchschnittlicher Score, Unternehmensscore, Marktpotenzial und Risiko;
   - interaktiven 3D-Potenzialraum mit Risiko auf X, Unternehmensscore auf Y, Marktpotenzial auf Z;
   - Stage-Verteilung als Ringdiagramm;
   - direkten Vergleich von Unternehmen, Markt und Risiko für die besten zehn;
   - anklickbare Ranking-Tabelle und Export des gesamten Analyselaufs.
4. Tabellenzeile oder „Startup kennenlernen“ öffnet eine eigene Detailansicht:
   Value Proposition, Investmenthypothese, Score-Profil, Unternehmensdaten, Risiken,
   Quellen, Gründer und Kontakt. Der Kontaktbutton öffnet einen Mailentwurf, versendet aber nichts.
5. **Zurück zur Übersicht** erhält die Top-N-Auswahl. **Neue Analyse** startet einen
   neuen Kategorieauftrag und verwirft alte Ergebnisse und die alte Detailauswahl.

Alle Scores: 0–100. Höhere Unternehmens-/Marktwerte sind besser; niedrigeres Risiko
ist besser. KPI-Mittelwerte und Stage-Verteilung beziehen sich auf die sichtbaren
Top-N-Startups, nicht auf die gesamte Ausgangsliste. Fehlende Scores sind unbekannt,
werden nicht als null gewertet und werden bei Mittelwerten ausgelassen. Unvollständige
3D-Punkte bleiben in der Tabelle. Demoberechnung ausschließlich im Fixture-Generator:
45 % Unternehmen + 35 % Markt + 20 % (100 − Risiko). Diese Formel muss das Team noch
fachlich abstimmen; das Dashboard übernimmt den fertigen Score.

## Architektur: vier Personen, vier Module

| Person | Modul | Vertrag |
| --- | --- | --- |
| 1 | sourcing/engine.py | search(SearchCriteria) → list[RawLead] |
| 2 | context/engine.py | enrich(RawLead) → EnrichedLead |
| 3 | evaluation/engine.py | evaluate(EnrichedLead) → EvaluatedLead |
| 4 | dashboard.py / deep_dive.py / charts.py | ResearchResult visualisieren |

`models.py` ist der gemeinsame Datenvertrag. `pipeline.run_pipeline(criteria)` führt
alle drei Engines aus und liefert **AnalysisRun** mit Schema-Version 2.0, Suchkriterien,
Modus, Zeitstempel, Anzahl gefundener/angereicherter Leads und `ResearchResult`.
`ResearchResult.leads` enthält die bewerteten Startups; `issues` enthält Fehler je Lead.
Sourcing filtert ausschließlich Branche und belegten Deutschland-Bezug, dedupliziert
nach ID und erhält die Fundreihenfolge. Kontext sammelt Fakten ohne Ranking.
Erst Bewertung sortiert nach `overall_score`. Fehlende Gesamt-Scores kommen zuletzt.

## Verbindliche Felder aus Schritt 1

| Fachliches Feld | JSON-/Python-Feld | Typ |
| --- | --- | --- |
| Name Gründer | founders | Liste von Namen |
| E-Mail | contact_email | primäre Kontaktadresse oder null |
| Name Unternehmen | name | Text |
| Website | website | HTTP(S)-URL oder null |
| Branche | industry | Wert aus Industry |
| Gründungsjahr | founding_year | Ganzzahl oder null |
| Gründungsmonat | founding_month | 1–12 oder null |
| Standort | location | Text oder null |
| VC-Beteiligung laut Sourcing | has_vc | true, false oder null |

Zusätzlich: `id`, `description` (kurze Fundbeschreibung), `country`, `source_name`,
`source_url`, `country_evidence`, `is_demo`. Die Quelle bleibt bis ins Dashboard erhalten.
Keine tiefe Recherche in Schritt 1: fehlende Kontaktangaben bleiben null, ein unbekannter
Gründungsmonat wird nicht erfunden. Eine .de-Domain allein belegt keinen deutschen Sitz.

**Änderung gegenüber v1:** Website, Gründer, E-Mail und Gründungsjahr/-monat liegen jetzt
bereits in RawLead, nicht erst in EnrichedLead. Alle bisherigen Felder werden vererbt.
Die Kontext-Engine darf diese Felder nicht erneut als zusätzliche Constructor-Argumente
übergeben; `EnrichedLead(**lead.model_dump(), evidence=...)` übernimmt sie bereits.

## Schritt 2: zusätzlicher Kontext

Schritt 2 lässt sich mit einer bestehenden Liste separat ausführen.

~~~powershell
python -m context shortlist.json dossiers.json
python -m context shortlist.json dossiers.json --ollama-model qwen3.5:4b
python -m context shortlist.json dossiers.json --offline --limit 10
~~~

Die Eingabe ist ein priorisiertes JSON-Array mit RawLead-Objekten inklusive
Deutschland-Beleg. Die CLI vertieft standardmäßig die ersten fünf Leads.
Sourcing kann `htgf_sector` und `prioritization_reason` mitgeben. Der optionale
HTGF-Sektor verwendet die fünf Track-Kategorien, während `industry` die
bestehende Produktkategorie bleibt.
Die Ausgabe ist ein ContextResult mit Dossiers in `leads` und Verarbeitungsfehlern
in `issues`. `collect_context(leads, use_mock=False)` liefert denselben Vertrag in Python.

Optional kann Sourcing pro Lead `signals` mitgeben. Ein Signal enthält `source`,
`type`, `url`, `date` (ISO-Datum oder null) und `evidence` (Quelltextauszug).
Online liest Schritt 2 zusätzlich die Startseite und bis zu vier von dort verlinkte
Unternehmensseiten sowie die ursprüngliche Fundseite, falls noch kein Auszug daraus
mitgeliefert wurde. Externe Bestätigungen können als weitere Signale mitgegeben werden.
Der Extraktor erkennt eindeutige deutsch- und englischsprachige
Angaben wie „Produktreife: MVP“, „Zielkunden: Industriebetriebe“ und
„Kim Muster – Rolle: CTO“. Bei freier Web-Sprache ist die Abdeckung begrenzt.
Mit `--ollama-model` kann ein lokal laufendes Modell für noch leere Textfelder
wörtliche Zitate ergänzen. Python prüft die Zitate gegen die übergebenen
Quellenausschnitte. Bei einem Modellfehler bleiben die regelbasierten Felder erhalten.

Die neuen Dossierfelder sind `founder_profiles` (Name, Rolle, Qualifikation),
`target_customers`, `customer_problem`, `solution`, `product_stage`, `funding_status`,
`vc_status` und `first_signal_date`. Das Dossier übernimmt alle Eingangsfelder.
Belege verknüpfen Aussagen mit Feldern und enthalten Quell-URL, Abrufdatum und,
falls mitgegeben, Publikations- bzw. Signaldatum. Bei widersprüchlichen Produkt- oder
Profilangaben bleiben die Werte leer und die konkurrierenden Belege erhalten.

`funding_status` erfasst auch Eigenfinanzierung, Förderung oder eine Finanzierung
unbekannter Art. `vc_status` bleibt ohne ausdrückliche Angabe `unknown`. Ein positives
VC-Signal bei anderslautender Sourcing-Angabe führt zu `conflicting`. Die Live-Pipeline
hält bestätigte und widersprüchliche VC-Fälle vor dem Scoring zurück und meldet den
Grund in `issues`. `unknown` ist bei Forschungsprojekten der Normalfall; solche Leads
werden bewertet und tragen die Frage nach den Investoren in `research_questions` mit.
Liegt eine Bundesförderung vor und kein VC-Signal, wird `funding_status` zu `non_vc_funded`.

### Live-Abfragen für das Scoring (Stand 20.11.2026)

Ohne `--offline`/`--no-lookups` fragt Schritt 2 je Lead feste öffentliche Quellen ab
und schreibt jedes Ergebnis mit eigener Quell-URL ins Dossier (Details und Grenzen in
`context/ENRICHMENT.md`):

| Quelle | Modul | Felder |
| --- | --- | --- |
| Impressum der Website | `context/imprint.py` | `imprint_url`, `legal_form`, `in_formation`, `managing_directors`, `register_id`, `imprint_email` |
| Förderkatalog des Bundes | `context/foekat.py` | `grants` (Programm, FKZ, Summe, Laufzeit), `match_confidence` |
| OpenAlex | `context/openalex.py` | je Gründer `institution`, `openalex_url`, `works_total`, `works_in_field`, `match_confidence` |
| Wayback CDX | `context/wayback.py` | `first_web_capture`, `in_databases`, `first_db_date`, `database_urls` |
| idw-online | `context/idw.py` | datierte Pressemeldungen als Signale, `founding_year_hint` |
| Texte (Regeln, optional Ollama) | `context/classify.py` | `product_stage`, `product_type`, `regulated_market`, `ip_status`/`patents`, `partners`, `business_model`, `market_size_eur`, `competitors` |
| Google Patents (nur mit `--patents`) | `context/patents.py` | `patents`, `ip_status` |

Alle Abrufe und Modellantworten laufen durch `.cache/context.db` (`--cache off` schaltet
ihn ab), damit ein zweiter Lauf dieselben Werte liefert; bei Modell-Timeouts kann ein
Zitatfeld im zweiten Lauf trotzdem fehlen. Was keine Quelle hat, bleibt `None` und geht im
Scoring neutral ein. `enrichment_sources` und `enrichment_errors` zeigen je Lead, welche
Abfragen liefen. Beispiel: `examples/context/real_leads.json` → `real_dossiers.json`
(vier echte Vorhaben, ca. 50 s je Lead inklusive Modell) → `examples/context/scores/`.

### Übergabe für Scorecard und VC Method

Das Dossier enthält zusätzlich Markt, Technologie, Wettbewerb, Vertrieb,
weiteren Kapitalbedarf, Rundengröße und geforderte Pre-Money-Bewertung. Fehlende
oder widersprüchliche Angaben bleiben offen. `research_questions` enthält dazu
Fragen für das Erstgespräch.

~~~powershell
python -m evaluation.valuation dossiers.json assumptions.json valuations.json
~~~

`assumptions.json` ordnet jeder Lead-ID die gewünschten Methodenannahmen zu.
Unter `scorecard` stehen `benchmark_pre_money_eur`, `benchmark_source`
und `factors`. Die sechs Faktoren `team`, `market`, `technology`,
`competition`, `sales` und `capital_need` benötigen jeweils `weight`,
`relative_score` und eine `rationale`. Die Gewichte summieren sich auf 1.
Ein relativer Faktor von 1 entspricht dem Benchmark.

Unter `vc_method` stehen `exit_equity_value_eur`, `future_dilution`
als Anteil zwischen 0 und 1 und `target_moic`. Der maximale Einstiegspreis
vor der Runde entspricht dem verwässerungsbereinigten Exit-Eigenkapitalwert
geteilt durch den Ziel-MOIC abzüglich der Rundengröße. Die Ausgabe zeigt
auch den Abstand zur Preisforderung. Fehlen Rundengröße oder Preisforderung,
bleibt dieser Methodenblock offen. Euro-Ergebnisse werden als Dezimalstrings
exportiert. Der Python-Rechenkern ist eine lokale Umsetzung der beiden
Methoden, ohne Abhängigkeit von einem externen Bewertungsdienst.

## Verbindliche Felder aus Schritt 3

| Fachliches Feld | JSON-/Python-Feld | Typ |
| --- | --- | --- |
| Score | overall_score | 0–100 oder explizit null |
| Risiko | risk_score | 0–100 oder explizit null; höher = riskanter |
| Marktpotenzialscore | market_potential_score | 0–100 oder explizit null |
| Unternehmensscore | company_score | 0–100 oder explizit null |
| Stage Einordnung | stage_classification | Pre-Seed / Seed / Early Growth / Unbekannt |
| Produktbeschreibung / Value Proposition | value_proposition | nicht leerer Text |
| Investmenthypothese | investment_thesis | Text |

Diese Felder müssen übergeben werden. Die alten quality_score, earliness_score und
confidence_score sind optionale Zusatzinformationen und kein Pflichtinput des Dashboards.
`funding_stage` bleibt eine Kontextangabe über die Finanzierung; `stage_classification`
ist die daraus und aus weiteren Fakten abgeleitete Einordnung aus Schritt 3.
`risks`, `score_drivers` und `open_questions` ergänzen den Deep Dive optional.

## Demo und Live-Integration

`demo_portfolio.py` enthält deterministische Fixtures und drei Adapter:
`demo_search`, `demo_enrich`, `demo_evaluate`. Sie liefern jeweils nur die Felder
ihres Prozessschritts. Die Demo durchläuft dieselben Pipeline-Funktionen wie die
spätere Live-Integration. Die UI verwendet aktuell `use_mock=True`.

`run_pipeline(criteria, use_mock=False)` verbindet die drei Live-Module.
Sourcing ist weiterhin ein Platzhalter; Kontext und Bewertung laufen live (Bewertung:
`scoring/SCORING.md`). Provider, Enricher und Evaluator lassen sich für Tests einzeln injizieren.
Fehler einzelner Kontext-/Bewertungsaufrufe verhindern nicht die restliche Verarbeitung.
Ein Totalausfall im Sourcing wird an die Oberfläche gemeldet.

Beispielübergabe: `examples/analysis-demo.json`.
Maschinenlesbares Schema: `examples/analysis-schema.json`.

## Dateien und Grenzen

- app.py: Kategorienwahl und Analyseauftrag, keine eigene Bewertungslogik.
- ui_theme.py / .streamlit/config.toml: Layout, Farben, Typografie.
- dashboard.py / charts.py: Visualisierungen und Ranking.
- deep_dive.py: Startup-Dossier und Kontakt.
- tests/: Verträge, Datenintegrität, Charts und kompletter Bedienablauf.

Die Sitzung liegt im Streamlit Session State. Ein vollständiger Browser-Reload kann
sie verwerfen. JSON-Export ist vorhanden; dauerhafte Speicherung und Import sind noch
offen. Detail-URLs `?startup=<ID>` funktionieren innerhalb eines vorhandenen Analyselaufs.

Visuelle Referenz: die vom Team bereitgestellte HTGF-Ansicht mit großer Typografie,
Weißraum, klaren Kennzahlen und dezenten Akzenten. FounderRadar verwendet eine eigene Marke.
Technik: [Streamlit](https://docs.streamlit.io/develop/api-reference/data/st.dataframe),
[Plotly](https://plotly.com/python/3d-scatter-plots/).
