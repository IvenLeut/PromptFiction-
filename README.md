# FounderRadar 2.0 - Investment Cockpit

Neuer Einstieg:

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

Ein zusammenhängender Ablauf für VC-Screening: **Kategorie auswählen → Analyse
starten → visualisierte Ergebnisse → Startup-Deep-Dive**.

Die Oberfläche zeigt pro Kategorie 30 fiktive Startups. Im Bereich Industrial / DeepTech
enthält `industrial-16` zusätzlich echte öffentliche Marktquellen und ein ausgewiesenes
Szenario zur Marktgröße. Schritt 2 lässt sich separat mit echten Leads ausführen.

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
| 3 | evaluation/engine.py | evaluate(ScoringInput, *, lead=EnrichedLead) → EvaluationScores |
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
python -m context longlist.json dossiers.json --light
~~~

Die Eingabe ist ein priorisiertes JSON-Array mit RawLead-Objekten inklusive
Deutschland-Beleg. Die CLI vertieft standardmäßig die ersten fünf Leads. Im Light-Modus
verarbeitet sie die gesamte Liste anhand der mitgelieferten Signale. `--lead ID` wählt
einen einzelnen Lead aus.
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

### Strukturierte Dossiers für Station 4

`context_v2` ergänzt die vorhandenen Felder um `company`, `founders`, `product`,
`traction`, `funding`, `discovery_signals`, `market_intelligence`, `research_status`
und `updated_at`. Aussagen referenzieren Belege über `evidence_ids`. Ein Beleg enthält
Abruf- und optional Dokumentdatum. `source_matched` bedeutet, dass der Extraktor
die Aussage im Quellenausschnitt gefunden hat. `source_reviewed` kennzeichnet
begutachtete Quellen, `assumption` gekennzeichnete Annahmen und `unverified`
übernommene, ungeprüfte Angaben. Das Feld `origin` unterscheidet Quellenaussagen,
vom Modell ausgewählte Zitate und Interpretation. Bestehende Exporte lassen sich
weiterhin validieren.

Traction unterscheidet zahlende Kunden, Kunden mit offenem Zahlstatus, bezahlte und
unbezahlte Piloten, LOIs, kommerzielle Partner und Forschungspartner. Öffentliche
Förderung hat einen eigenen Abschnitt. Ein angegebener Förderantrag verändert den
VC-Status nicht.

### Gezielte Marktrecherche

~~~powershell
python -m context shortlist.json dossier.json --lead <ID> --market-input marktquellen.json
python -m context shortlist.json dossier.json --lead <ID> --market-source <URL>
~~~

`--market-input` erwartet ein Objekt gemäß `examples/market-input-schema.json` mit
strukturierten Marktwerten und Belegen. `--market-source` kann bis zu sechs öffentliche
HTML-Seiten lesen und erkennbare qualitative Angaben übernehmen. Beide Optionen sind
kombinierbar. Der Abruf verwendet einen Cache von bis zu 64 Seiten in 15-Minuten-Fenstern.
Für amtliche Statistiken, Wettbewerber und Transaktionen können geprüfte Eingaben mit
Originalquelle übergeben werden. Der Workflow sucht keine zusätzlichen Quellen im
offenen Web und setzt keinen Zugang zu kostenpflichtigen Datenbanken voraus.

Für Bottom-up-Berechnungen enthält `sizing_inputs` die Teilwerte
`addressable_companies` (Unternehmen), `annual_revenue_per_company`
(pro Unternehmen und Jahr), `serviceable_share` (Anteil 0–1) und
`delivery_capacity` (Unternehmen). Alle Werte eines Szenarios verwenden dieselbe
Geografie und Periode. Der SOM nutzt die kleinere Anzahl aus Kapazität und SAM.
Fehlende Marktwerte bleiben offen. Zeitreihen führen beobachtete Werte getrennt
von Prognosen und Annahmen. CAGR setzt vergleichbare Jahreswerte voraus.
Transaktionsmultiples erfordern explizit veröffentlichten Enterprise Value und
eine positive, vergleichbare Jahreskennzahl. Die HTGF-Matrix erhält TRL und eine
begründete Marktsicherheit, wenn diese strukturiert und mit Belegen vorliegen.

Im Deep Dive von `industrial-16` zeigt der Tab **Marktrecherche** die Eurostat-Reihe
zur Unternehmensbasis, das TAM-/SAM-/SOM-Szenario, drei Wettbewerber und eine
veröffentlichte HTGF-Referenzrunde. Die Grundgesamtheit bildet eine Obergrenze,
der Preis und die Reichweite sind Annahmen. Eine belastbare Marktumsatzreihe und
eine Prognose stehen für dieses Beispiel offen.

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
spätere Live-Integration. Standardmäßig verwendet die UI `use_mock=True`.

`run_pipeline(criteria, use_mock=False)` verbindet die drei Live-Module.
Das Sourcing verwendet einen konfigurierten Screening-Export, dessen bestätigte
Leads zur gewählten Kategorie passen. Die Feldbelege bleiben bis ins Dossier erhalten.
Kontext und Bewertung laufen live (Bewertung:
`scoring/SCORING.md`). Provider, Enricher und Evaluator lassen sich für Tests einzeln injizieren.
Fehler einzelner Kontext-/Bewertungsaufrufe verhindern nicht die restliche Verarbeitung.
Ein Totalausfall im Sourcing wird an die Oberfläche gemeldet.

Für einen vorhandenen Screening-Bericht kann die Oberfläche im Live-Modus starten.

~~~powershell
$env:FOUNDERRADAR_MODE = 'live'
$env:FOUNDERRADAR_SCREENING_REPORT = 'climate.json'
python -m streamlit run app.py
~~~

Für die Kommandozeile akzeptiert der Kontext-Schritt den Bericht direkt:

~~~sh
python -m context climate.json dossiers.json --light --offline --scoring-output scoring.json
python -m scoring dossiers.json --out scores
~~~

Beispielübergabe: `examples/analysis-demo.json`.
Maschinenlesbares Schema: `examples/analysis-schema.json`.

Der [Datenvertrag für Schritt 3](SCORING_HANDOFF.md) beschreibt den
standardisierten Export und den reproduzierbaren Offline-Aufruf.

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
