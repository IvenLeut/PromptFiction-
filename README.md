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

Zusätzlich: `id`, `description` (kurze Fundbeschreibung), `country`, `source_name`,
`source_url`, `country_evidence`, `is_demo`. Die Quelle bleibt bis ins Dashboard erhalten.
Keine tiefe Recherche in Schritt 1: fehlende Kontaktangaben bleiben null, ein unbekannter
Gründungsmonat wird nicht erfunden. Eine .de-Domain allein belegt keinen deutschen Sitz.

**Änderung gegenüber v1:** Website, Gründer, E-Mail und Gründungsjahr/-monat liegen jetzt
bereits in RawLead, nicht erst in EnrichedLead. Alle bisherigen Felder werden vererbt.
Die Kontext-Engine darf diese Felder nicht erneut als zusätzliche Constructor-Argumente
übergeben; `EnrichedLead(**lead.model_dump(), evidence=...)` übernimmt sie bereits.

## Schritt 2: zusätzlicher Kontext

EnrichedLead enthält alle RawLead-Felder plus Quellenbelege, Finanzierungsdaten,
Teamgröße, Produktstatus, Kunden, Umsatz und Traktionsnotizen. Fehlende Daten bleiben
None. Neue Rechercheaussagen und Widersprüche werden als Evidence dokumentiert;
Eingangsdaten werden nicht still überschrieben. Jeder Beleg enthält Quelle, URL,
Aussage, Abrufdatum und optional das zugehörige Feld.

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

`run_pipeline(criteria, use_mock=False)` verbindet die drei echten Engine-Dateien.
Diese enthalten weiterhin ausdrückliche Platzhalter. Es gibt keinen stillen Rückfall
auf erfundene Daten. Provider, Enricher und Evaluator lassen sich für Tests einzeln injizieren.
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
