# FounderRadar

Lokales Python-/Streamlit-Grundgerüst zum VC-Screening deutscher Early-Stage-Startups.
**Status: Demo-Prototyp. Echte Such-, Scraping- und Bewertungsanbieter sind noch nicht angeschlossen.**
Alle Demo-Unternehmen, Quellen und Bewertungen sind fiktiv.

## Start unter Windows

Python 3.11 oder neuer, dann im Projektverzeichnis:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Dashboard: http://localhost:8501. Keine API-Schlüssel im Demo-Modus nötig.
Tests: `.\.venv\Scripts\python.exe -m pytest -q`

## Vier Schritte

1. **Branche auswählen / Sourcing:** `discover(SearchCriteria) -> list[RawLead]`.
   Nur deutsche Standorte mit Beleg aus der Fundquelle und passender Branche.
   Deduplizierung nach ID und Trefferlimit; keine Kontext-Recherche oder Sortierung.
   Unklarer Deutschland-Bezug wird ausgeschlossen; eine .de-Domain genügt nicht.
2. **Kontext scrapen:** `collect_context(raw_leads) -> ContextResult`.
   Liefert EnrichedLead mit Kennzahlen und Quellen. Unbekannte Werte bleiben None.
   Keine Scores; Reihenfolge bleibt erhalten.
3. **Berechnen / bewerten:** `evaluate_context(enriched_leads) -> ResearchResult`.
   Qualität, Earliness, Konfidenz, Investment-These, Risiken und finales Ranking.
   Erst hier wird Early-Stage-Eignung bewertet.
4. **Dashboard / Visualisierung:** `app.py` stellt die bewerteten Leads aus
   `ResearchResult` als Ranking mit Scores, Detailansichten, Investment-Thesen,
   Risiken und Quellen dar. Die Darstellung berechnet keine eigenen Bewertungen.

Die Schritte 1 bis 3 werden ausdrücklich in der Oberfläche gestartet. Schritt 4
zeigt anschließend automatisch die fertigen Ergebnisse. Neue Suche löscht nachgelagerte
Ergebnisse. Ein neuer Kontextlauf löscht die bisherige Bewertung.

## Zuständigkeiten

| Datei | Vertrag / Aufgabe |
| --- | --- |
| models.py | Gemeinsame Pydantic-Verträge; Änderungen im Team abstimmen |
| sourcing/engine.py | search(criteria) -> list[RawLead]; Discovery-Anbieter integrieren |
| context/engine.py | enrich(raw) -> EnrichedLead; Scraping und Normalisierung |
| evaluation/engine.py | evaluate(enriched) -> EvaluatedLead; Bewertungslogik |
| pipeline.py | Stufengrenzen, Filter, Fehlerisolierung, finales Ranking |
| mock_data.py | Fiktive Engines zur unabhängigen Entwicklung |
| app.py | Schritt 4: Ergebnis-Dashboard; außerdem Bedienung der Schritte 1 bis 3 und JSON-Export |
| tests/ | Pipeline-Verträge und Dashboard-Ablauf |

Alle Engines bleiben unabhängig von Streamlit. Die Pipeline akzeptiert auch injizierte
Provider-Funktionen für Tests. use_mock=False nutzt echte Engines; die Platzhalter
melden ausdrücklich fehlende Implementierung. Kein stiller Rückfall auf Demo-Daten.
Die Oberfläche bleibt bis zur Integration im Demo-Modus.

## Kontextfelder für Schritt 3

| Feld | Bedeutung / Einheit |
| --- | --- |
| website, location, founders | Website, Standort, Teamnamen |
| founded_on, team_size | Gründungsdatum, Anzahl Mitarbeitende |
| funding_stage, funding_total_eur, last_funding_on | Phase, kumulierte Finanzierung EUR, Datum |
| product_stage | Idee, Prototyp, MVP, Marktstart etc. |
| customer_count, annual_revenue_eur, traction_notes | Kunden, Jahresumsatz EUR, Traktion |
| evidence | Quelle, HTTP(S)-URL, Aussage, optionaler Feldname, Abrufzeitpunkt |

Erster Vorschlag für den gemeinsamen Vertrag: Jeder gescrapte Fakt soll einen
zugehörigen Evidence-Eintrag erhalten. Fehlende Werte bleiben unbekannt, nicht null.
Währungen normalisieren und Umrechnung belegen. Folgemodule dürfen Eingangsdaten
nicht überschreiben; Widersprüche als Beleg erfassen. Bewertungsgewichte und genaue
Early-Stage-Definition müssen noch fachlich festgelegt werden. Demo-Scores sind
feste Testwerte und keine echte Bewertungsformel.

## Speicherung / nächste Integrationen

Der Stand lebt pro Browsersitzung im Session State und kann als versioniertes JSON
exportiert werden. Ein Reload verliert die Sitzung. Dauerhafte Speicherung und Import
sind noch nicht implementiert. Keine Datenbank oder Zugangsdaten erforderlich.

Nächste Aufgaben: Discovery-Quellen wählen; Scraper mit Timeouts, Quellenbelegen und
normalisierten Kennzahlen implementieren; Bewertungsformel definieren; echte Engines
verbinden; dauerhafte Speicherung ergänzen.

Referenzen: [Streamlit Session State](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state),
[Streamlit Forms](https://docs.streamlit.io/develop/api-reference/execution-flow/st.form),
[Pydantic Models](https://pydantic.dev/docs/validation/latest/concepts/models/).
