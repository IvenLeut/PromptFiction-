# Kontext-Schritt: Anreicherung für das Scoring

Ziel: Jedes Dossier (`models.EnrichedLead`) bekommt die Felder, die das Scoring (`scoring/`) bewertet, **jedes mit eigener Quellen-URL**. Was keine Quelle hat, bleibt `None` oder leer und geht im Scoring neutral ein. Es wird nichts geraten.

## Regeln für alle Module

- Ein Modul = eine Datei in `context/`, eine Testdatei `tests/test_context_<modul>.py`, Fixtures in `tests/fixtures/context/`.
- Externe Aufrufe nur über `context.http.request` / `get_json` (feste Hosts) oder `context.web.fetch` (Unternehmenswebsite, mit Same-Site-Schutz). Beide bekommen das `cache`-Objekt (`context.cache.Cache`) durchgereicht.
- Tests laufen **offline**: echte Antworten einmal mitschneiden, gekürzt als Fixture ablegen, im Test den Abruf injizieren (`fetch=`-Parameter) oder `context.http.request` monkeypatchen. Kein Netz in `pytest`.
- Jede Funktion gibt entweder Pydantic-Objekte aus `models.py` zurück (`Grant`, `Partner`, `Patent`, `FounderProfile`) oder ein `Lookup`-Ergebnis (siehe unten). Fehler werden nicht geworfen, sondern als `errors` zurückgegeben.
- Keine persönlichen Daten in Requests (keine E-Mail als `mailto`, generischer User-Agent).
- Rate-Limits einhalten (`min_interval` in `context.http.request`), Antworten begrenzen, Timeouts setzen.
- Python 3.12, Stdlib + pydantic. Keine neuen Abhängigkeiten ohne Rücksprache.

## Gemeinsames Rückgabeformat

```python
@dataclass
class Lookup:
    fields: dict            # Feldname -> Wert, nur belegte Felder (Feldnamen wie in EnrichedLead)
    evidence: list[Evidence] # je Feld mindestens ein Evidence(field=<Feldname>, url=..., finding=<Zitat/Auszug>, source=<Dienst>, source_date=...)
    signals: list[SourceSignal]  # neue Rohtexte (z. B. Impressum-Seite, idw-Meldung) für spätere Extraktion
    errors: list[str]       # z. B. "openalex: HTTP 429", leer wenn alles lief
```

`context/lookup.py` stellt die Klasse bereit. Listenfelder (`grants`, `partners`, `patents`, `founder_profiles`) tragen ihre URL im Objekt selbst; ein zusätzlicher Evidence-Eintrag ist trotzdem erwünscht.

## Module und Signaturen

| Modul | Funktion | Liefert |
|---|---|---|
| `context/imprint.py` | `imprint_lookup(website: str, *, cache, fetch=None) -> Lookup` | `imprint_url`, `legal_form`, `in_formation`, `managing_directors`, `register_id`, `contact_email` (nur generische Postfächer; landet als `imprint_email` im Dossier, weil `contact_email` ein Schritt-1-Feld ist), Signal `typ="impressum"` mit dem Seitentext |
| `context/openalex.py` | `author_lookup(name: str, *, institution: str \| None, field_terms: list[str], cache, fetch=None) -> tuple[FounderProfile \| None, Lookup]` | `openalex_url`, `institution`, `works_total`, `works_in_field`, `match_confidence` (Namens-/Institutions-Treffer) |
| `context/foekat.py` | `grant_lookup(name: str, *, institution: str \| None, reference: str \| None, cache, fetch=None) -> tuple[list[Grant], Lookup]` | EXIST- und andere Bundesförderungen mit FKZ, Summe, Laufzeit, Detail-URL; Signal `typ="exist_projekt"` mit Thema/Beschreibung |
| `context/wayback.py` | `web_history_lookup(website: str \| None, name: str, *, cache, fetch=None) -> Lookup` | `first_web_capture`, `in_databases`, `first_db_date`, `database_urls` (Crunchbase/Dealroom-Profil-URLs über CDX, ohne Wildcards) |
| `context/classify.py` | `classify_texts(name: str, signals: list[SourceSignal], *, model: str \| None, cache, ask=None, founders=()) -> Lookup` | Regel-Extraktion plus optional Ollama (`qwen3.5:4b`, `think:false`, `temperature:0`, JSON-Schema): `product_stage` (nur wenn `context.engine` nichts fand), `product_type`, `regulated_market`, `ip_status`+`patents`, `partners`, `market_size_eur`, `business_model`, `competitors`. **Jeder Modellwert braucht ein wörtliches Zitat, das Python per Substring-Prüfung im Quelltext findet; sonst wird er verworfen.** |
| `context/engine.py` | `enrich(lead, *, ..., lookups=None)` | ruft die Module auf, führt die Ergebnisse zusammen, füllt `enrichment_sources` / `enrichment_errors` / `research_questions` |
| `context/idw.py` | `idw_lookup(name, *, institution, founders, cache, fetch=None) -> Lookup` | datierte Pressemeldungen als Signale `typ="idw"`, Evidence `founding_statement`/`grants_mention`/`ip_mention`, `founding_year_hint` |
| `context/patents.py` | `patent_lookup(company, founders, *, cache, fetch=None, budget=None) -> tuple[list[Patent], Lookup]` | Google Patents, nur mit `--patents` (IP-Sperre nach ~12 Anfragen); nie `keine` aus einem leeren Ergebnis |

Texte, die nicht eindeutig von der Firma handeln (Pressemeldungen, in denen der Name nur einmal vorkommt), werden nur satzweise rund um den Firmen- oder Gründernamen ausgewertet.

## Offene Grenzen (dokumentieren, nicht umgehen)
- OpenAlex ohne Key: etwa 100 Anfragen pro Tag und IP (2 je Gründer). Ein kostenloser Key braucht eine E-Mail-Adresse des Teams.

- Patente: ohne API-Key gibt es keine verlässliche Abfrage. `ip_status` kommt nur aus Website-/Pressetext mit Zitat.
- Marktvolumen steht selten auf der Website; bleibt meist `None`.
- Projektname → Firma ist mehrdeutig. `match_confidence` zeigt das an; Werte unter 0,5 werden im Scoring als unsichere Zuordnung behandelt.
