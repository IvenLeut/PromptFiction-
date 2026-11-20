# Beispieldateien

Alle Befehle laufen im Projektordner mit aktivierter venv (`python` = `.venv/bin/python` bzw.
`.\.venv\Scripts\python.exe`). „Netz“ heißt: ohne gefüllten `.cache/context.db` werden öffentliche Quellen
abgefragt, das Ergebnis kann sich dann ändern.

## Schemas (aus den Modellen erzeugt)

| Datei | Modell | Geprüft von |
| --- | --- | --- |
| `analysis-schema.json` | `models.AnalysisRun` (Dashboard-Vertrag, Schritte 1–3) | `tests/test_contracts.py` |
| `context-schema.json` | `models.ContextResult` (Ausgabe Schritt 2) | `tests/test_contracts.py` |
| `scoring-input-schema.json` | `list[scoring_models.ScoringInput]` (Export `--scoring-output`) | `tests/test_contracts.py` |
| `market-input-schema.json` | `research_models.MarketIntelligence` (`--market-input`) | – |

Nach jeder Modelländerung neu erzeugen (`tests/test_contracts.py` schlägt sonst fehl):

```bash
python -c "import json, models; open('examples/analysis-schema.json','w',encoding='utf-8').write(json.dumps(models.AnalysisRun.model_json_schema(), indent=2, ensure_ascii=False)+'\n')"
python -c "import json, models; open('examples/context-schema.json','w',encoding='utf-8').write(json.dumps(models.ContextResult.model_json_schema(), indent=2, ensure_ascii=False)+'\n')"
python -c "import json, scoring_models; from pydantic import TypeAdapter; open('examples/scoring-input-schema.json','w',encoding='utf-8').write(json.dumps(TypeAdapter(list[scoring_models.ScoringInput]).json_schema(), indent=2, ensure_ascii=False)+'\n')"
python -c "import json, research_models; open('examples/market-input-schema.json','w',encoding='utf-8').write(json.dumps(research_models.MarketIntelligence.model_json_schema(), indent=2, ensure_ascii=False)+'\n')"
```

## Daten

| Datei | Inhalt | Erzeugt mit | Gelesen von |
| --- | --- | --- | --- |
| `analysis-demo.json` | Exportierter Demo-Lauf (`AnalysisRun`, AI / Software, 30 fiktive Startups) | `python -c "from models import Industry, SearchCriteria; from pipeline import run_pipeline; open('examples/analysis-demo.json','w',encoding='utf-8').write(run_pipeline(SearchCriteria(industry=Industry.AI, limit=30), use_mock=True).model_dump_json(indent=2)+'\n')"` (offline; entspricht dem Export-Button) | README |
| `scoring-leads.json` | Ein fiktiver Lead für den ScoringInput-Export (Pilotstatus, Nullumsatz 2023, zwei abweichende Umsätze 2024) | von Hand | `SCORING_HANDOFF.md` |
| `sourcing/shortlist.json` | Vollständige Fundliste Schritt 1, Stand 20.11.2026: 733 EXIST-Leads, nach Priorität sortiert (1,8 MB) | `python -m sourcing foekat --since 2024-01-01 --out examples/sourcing/shortlist.json` (Netz; mit Cache byte-identisch) | `sourcing/FOEKAT.md` (Zahlen, Beispiel-Lead), README |
| `sourcing/sample_leads.json` | Acht Leads aus `shortlist.json` (beide Programme, verschiedene Branchen) | von Hand ausgewählt | README (Offline-Lauf) |
| `sourcing/sample_dossiers.json` | `ContextResult` der acht Leads (Live-Lauf 20.11.2026, mit Ollama-Zitaten; Modell nicht protokolliert) | `python -m context examples/sourcing/sample_leads.json examples/sourcing/sample_dossiers.json --limit 8 --ollama-model <Modell>` (Netz), danach von Hand gekürzt (siehe Datenschutz) | `tests/test_dashboard.py`, `tests/test_scoring.py` (Anzahl 8 und Inhalte), `scoring/SCORING.md` |
| `context/real_leads.json` | Vier echte Vorhaben mit Website und Gründernamen | von Hand | README |
| `context/real_dossiers.json` | `ContextResult` der vier Vorhaben | `python -m context examples/context/real_leads.json examples/context/real_dossiers.json --ollama-model <Modell>` (Netz, ca. 50 s je Lead inklusive Modell) | `scoring/SCORING.md` |
| `context/scores/` | Scores der vier Vorhaben (`scores.json`, `scores.csv`, `scores.schema.json`) | `python -m scoring examples/context/real_dossiers.json --out examples/context/scores --stichtag 2026-11-20` (offline) | `scoring/SCORING.md` |
| `scoring/` | Scores der erfundenen Dummy-Leads | `python -m scoring scoring/testleads/dummy_leads.json --out examples/scoring --stichtag 2026-11-20` (offline) | `scoring/SCORING.md` |

`scores.schema.json` in beiden Score-Ordnern ist eine Kopie von `scoring/scores.schema.json`, die die
Scoring-CLI in jeden Zielordner schreibt.

Scores der acht Förderkatalog-Leads: `python -m scoring examples/sourcing/sample_dossiers.json --out scoring_out`.
Das Scoring-Dossierformat (deutsche Feldnamen), das die CLI intern aus einem `ContextResult` baut:
`python -c "import json; from scoring.sources import load_dossiers; print(json.dumps(load_dossiers('examples/context/real_dossiers.json'), indent=2, ensure_ascii=False))"`.

## Datenschutz

- E-Mail-Adressen: nur das generische Impressumspostfach `info@kiutra.com` (`context/`), sonst `@example.org`
  (fiktiv). Keine Telefonnummern, keine privaten Anschriften.
- Personennamen: Geschäftsführung laut Impressum (Pflichtangabe, `context/real_dossiers.json`),
  Projektleitungen aus Förderkatalog und idw-Pressemitteilungen (`sourcing/sample_dossiers.json`) sowie die
  Gründernamen in `context/real_leads.json`. Die Gründerrolle dieser Namen ist von Hand eingetragen und nicht
  durch eine mitgelieferte Quelle belegt; die Verantwortlichen sollten sie belegen oder pseudonymisieren.
- `sourcing/sample_dossiers.json`: Eine idw-Meldung enthielt eine Gesundheitsangabe zu einer namentlich
  genannten Person (Art. 9 DSGVO); der Satz ist durch `[gekürzt: Gesundheitsangabe zu einer Person entfernt]`
  ersetzt. Ein neuer Live-Lauf holt den vollständigen Text wieder und muss erneut gekürzt werden.
