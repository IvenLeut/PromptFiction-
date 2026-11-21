# Kontext-Schritt: Anreicherung für das Scoring

Ziel: Jedes Dossier (`models.EnrichedLead`) bekommt die Felder, die das Scoring (`scoring/`) bewertet, **jedes mit eigener Quellen-URL**. Was keine Quelle hat, bleibt `None` oder leer und geht im Scoring neutral ein. Es wird nichts geraten.

## Regeln für alle Module

- Ein Modul = eine Datei in `context/`, eine Testdatei `tests/test_context_<modul>.py`, Fixtures in `tests/fixtures/context/`.
- Externe Aufrufe nur über `context.http.request` / `get_json` (feste Hosts) oder `context.web.fetch` (Unternehmenswebsite, mit Same-Site-Schutz). Beide bekommen das `cache`-Objekt (`context.cache.Cache`) durchgereicht.
- Tests laufen **offline**: echte Antworten einmal mitschneiden, gekürzt als Fixture ablegen, im Test den Abruf injizieren (`fetch=`-Parameter) oder `context.http.request` monkeypatchen. Kein Netz in `pytest`.
- Jede Funktion gibt entweder Pydantic-Objekte aus `models.py` zurück (`Grant`, `Partner`, `Patent`, `FounderProfile`) oder ein `Lookup`-Ergebnis (siehe unten). Fehler werden nicht geworfen, sondern als `errors` zurückgegeben.
- Keine persönlichen Daten in Requests (keine E-Mail als `mailto`, generischer User-Agent).
- Rate-Limits einhalten (`min_interval` in `context.http.request`), Antworten begrenzen, Timeouts setzen. Die Werte stehen als Konstanten (`TIMEOUT`, `MIN_INTERVAL`, `MAX_REQUESTS`) oben im jeweiligen Modul, siehe Tabelle „Grenzen“.
- `source`-Bezeichnungen der Evidence/Signale stehen einmal in `context/lookup.py` (`SOURCE_FOEKAT = "Förderkatalog"`, `SOURCE_IDW_MENTION = "idw (Erwähnung)"`, `MODEL_QUOTE_PREFIX = "Ollama-Zitat aus "` …). Die Werte nicht ändern: `evaluation/engine.py` prüft auf `"Ollama-Zitat"` und `"(Erwähnung)"`.
- Gemeinsame Text-Helfer (Umlauttabelle, Rechtsform-Muster, deutsches Datum, `years_before`, `strip_persons`) liegen in `context/text.py`; bewusst abweichende Varianten (Namensfaltung je Dienst, Betragsparser) sind dort im Docstring aufgeführt.
- Python 3.11 oder neuer, Stdlib + pydantic. Keine neuen Abhängigkeiten ohne Rücksprache.

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
| `context/engine.py` | `enrich(lead, *, load_pages=company_pages, load_original=None, extract_quotes=None, light=False, lookups=None, as_of=None) -> EnrichedLead` | ruft die Module auf, führt die Ergebnisse zusammen, füllt `enrichment_sources` / `enrichment_errors` / `research_questions`; `light=True` ruft keine externen Dienste |
| `context/engine.py` | `default_lookups(cache=<Standard>, model=None, patents=False) -> dict` | die Live-Lookups als Callables plus `"cache"` und `"model"`. Ohne `cache`-Argument: gemeinsamer Datei-Cache `Cache()` (`.cache/context.db` bzw. `$CONTEXT_CACHE`; so ruft `pipeline.py` auf, das CLI übergibt `Cache(--cache)`). `cache=None` → `NoCache()`, berührt die Platte nicht (Tests). `patents=True` schaltet Google Patents ein |
| `context/engine.py` | `parse_catalogue(text) -> dict \| None`, `catalogue_grant(signal) -> tuple[Grant, Evidence, dict] \| None` | liest das beschriftete Katalogsignal aus Schritt 1 (`Förderkennzeichen:` …, auch das alte einzeilige `FKZ …;`-Format) **offline** zu einem `Grant` mit Evidence `field="grants"`; läuft in allen Modi, auch `--light`. Ein per Lookup gefundener Grant mit derselben FKZ hat Vorrang. Personennamen in Förderempfänger/Ausführender Stelle werden entfernt (`strip_persons`) |
| `context/imprint.py` | `imprint_lookup(website: str, *, cache, fetch=None) -> Lookup` | `imprint_url`, `legal_form`, `in_formation`, `managing_directors`, `register_id`, `contact_email` (nur generische Postfächer; landet als `imprint_email` im Dossier, weil `contact_email` ein Schritt-1-Feld ist), Signal `type="impressum"` mit dem Seitentext |
| `context/openalex.py` | `author_lookup(name: str, *, institution: str \| None, field_terms: list[str], cache, fetch=None) -> tuple[FounderProfile \| None, Lookup]` | `openalex_url`, `institution`, `works_total`, `works_in_field`, `match_confidence` (Namens-/Institutions-Treffer); nur mit Gründernamen |
| `context/foekat.py` | `grant_lookup(name: str, *, institution: str \| None, reference: str \| None, cache, fetch=None) -> tuple[list[Grant], Lookup]` | EXIST- und andere Bundesförderungen mit FKZ, Summe, Laufzeit, Detail-URL; Signal `type="exist_projekt"` (andere Bundesförderung: `"foerderprojekt"`). `reference` = FKZ aus dem Katalogsignal (exakte Abfrage). Förderempfänger und Ausführende Stelle ohne Personennamen (`context.text.strip_persons`: „Prof. Dr. …“, „AG Vorname Nachname“; Institutsbezeichnungen und Fach-AGs wie „AG Künstliche Intelligenz“ bleiben) in `Grant.recipient`, Evidence, Signal und `institution` |
| `context/wayback.py` | `web_history_lookup(website: str \| None, name: str, *, cache, fetch=None, not_before: date \| None = None) -> Lookup` | `first_web_capture`, `in_databases`, `first_db_date`, `database_urls` (Crunchbase/Dealroom über CDX, ohne Wildcards). Erste Erfassung mehr als `WEB_NAMESAKE_YEARS` (1 Jahr) vor `not_before` → Namensvetter, nicht gezählt, Eintrag in `errors` |
| `context/classify.py` | `classify_texts(name: str, signals: list[SourceSignal], *, model: str \| None, cache, ask=None, founders=(), exclude_names=()) -> Lookup` | Regel-Extraktion plus optional Ollama (`qwen3.5:4b`, `think:false`, `temperature:0`, JSON-Schema): `product_stage` (nur wenn `context.engine` nichts fand), `product_type`, `regulated_market`, `ip_status`+`patents`, `partners`, `market_size_eur`, `business_model`, `competitors`. **Jeder Modellwert braucht ein wörtliches Zitat, das Python per Substring-Prüfung im Quelltext findet; sonst wird er verworfen.** `exclude_names` (Förderempfänger/Ausführende Stelle des Leads) und personenartige Namen werden nie Partner. Typen in `NO_QUOTE_TYPES` (u. a. `exist_projekt`) gehen nie ans Modell |
| `context/idw.py` | `idw_lookup(name, *, institution, founders, cache, fetch=None) -> Lookup` | datierte Pressemeldungen als Signale `type="idw"`; Evidence `idw` (Artikel über den Lead) bzw. `idw_mention` (nur Erwähnung, `source="idw (Erwähnung)"`, zählt im Scoring nicht als datiertes Signal), `founding_statement`/`grants_mention`/`ip_mention`, `founding_year_mention` + `founding_year_hint` |
| `context/patents.py` | `patent_lookup(company, founders, *, cache, fetch=None, budget=None) -> tuple[list[Patent], Lookup]` | Google Patents, nur mit `--patents` (IP-Sperre nach ~12 Anfragen); nie `keine` aus einem leeren Ergebnis |

Texte, die nicht eindeutig von der Firma handeln (Pressemeldungen, in denen der Name nur einmal vorkommt), werden nur satzweise rund um den Firmen- oder Gründernamen ausgewertet.

## Institution und Namensvetter (`context/engine.py`)

- **Institution:** Der erste Teil des Förderempfängers aus dem Katalogsignal (z. B. „Technische Universität München (TUM)“) geht als `institution` an `grant_lookup`, `idw_lookup` und `author_lookup`; sonst Impressum, Standort oder der Empfänger eines gefundenen Grants.
- **idw:** Namen treffen nur als ganzes Wort („sensAI“ nie in „BiosenSAI“); ein Artikel, der weder den Lead noch zwei Gründer-Nachnamen nennt, fällt weg. Artikel, die mehr als 2 Jahre vor dem frühesten datierten Sourcing-Signal (z. B. EXIST-Projektbeginn) erschienen (`PRESS_NAMESAKE_YEARS`), gelten als Namensvetter: Signal und Evidence werden verworfen, `errors` nennt die URL.
- **Wayback/Datenbanken:** `not_before` = frühestes Sourcing-Signal (Grenze `WEB_NAMESAKE_YEARS` = 1 Jahr, siehe Tabelle).
- **Warum zwei Grenzen** (`context/lookup.py`): Domain und Crunchbase-/Dealroom-Profil eines Start-ups entstehen mit dem Vorhaben; eine Aufnahme ein Jahr davor ist eine geparkte Domain oder ein Slug-Namensvetter. Forschungsgruppen veröffentlichen Ergebnisse (idw, „wurde gegründet“) dagegen oft ein bis zwei Jahre vor dem EXIST-Projekt; das engere Fenster würde echte Artikel verwerfen.
- **Gründungsjahr-Hinweis:** `founding_year_hint` aus einem idw-Satz mit Leadname und Jahr („2018 gegründet“) wird verworfen, wenn das Jahr mehr als `PRESS_NAMESAKE_YEARS` (2) Jahre vor dem ersten Signal liegt. Ohne Jahr gilt das Erscheinungsjahr einer `founding_statement`, wenn der Satz den Lead nennt, „gegründet“/„founded“ sagt, keine Planung beschreibt („soll“, „in Gründung“ …), der Artikel vom Lead handelt (Name im Titel oder mindestens zweimal) und dieselbe Plausibilitätsgrenze hält.
- `first_signal_date` ignoriert reine Erwähnungen (`idw (Erwähnung)`).

## Offene Grenzen (dokumentieren, nicht umgehen)

- OpenAlex ohne Key: etwa 100 Anfragen pro Tag und IP (2 je Gründer). Ein kostenloser Key braucht eine E-Mail-Adresse des Teams. Für EXIST-Leads aus dem Förderkatalog irrelevant: sie haben keine Gründer, OpenAlex wird nicht abgefragt.
- Patente: ohne API-Key gibt es keine verlässliche Abfrage. `ip_status` kommt nur aus Website-/Pressetext mit Zitat.
- Marktvolumen steht selten auf der Website; bleibt meist `None`.
- Projektname → Firma ist mehrdeutig. `match_confidence` zeigt das an; Werte unter 0,5 werden im Scoring als unsichere Zuordnung behandelt.
- `strip_persons` ist eine Heuristik (`context/text.py`, eine Funktion für beide Schritte; `sourcing/mapping.py` importiert sie): ein Personenname ohne Titel und ohne vorangestelltes „AG“ bleibt stehen. Besteht das Feld nur aus einer Person, wird es leer.

## Caching

Alle dauerhaften Ebenen teilen ein `Cache`-Objekt (`lookups["cache"]`); die vollständige Liste (Schlüssel, Umfang) steht im Docstring von `context/cache.py`:

- `context.http.request` (idw, OpenAlex, Wayback, Google Patents), `context.foekat`, `context.web.fetch` (Website und Impressum-Seiten, auch Fehlschläge), `context.imprint`, `context.classify` (Modellantworten), `context.engine.cached_quotes` (Ollama-Zitate, `context.ollama.extract_quotes` bleibt unverändert).
- Im Prozess zusätzlich `lru_cache` in `context.web._fetch_window` (15 Minuten) und `context.ollama.request_quotes`. Sie greifen auch ohne `Cache` (`--no-lookups`) und sind deshalb keine Doppelung.
- Gültigkeit 14 Tage (`ttl_hours`), `CONTEXT_CACHE=off` oder `--cache off` schaltet ab.

## Grenzen

| Dienst | Anfragen je Lead | Abstand | Timeout |
|---|---|---|---|
| Unternehmenswebsite (`context.web`) | 5 Seiten (`MAX_PAGES`), 4 Weiterleitungen, 512 KB | – | 4 s |
| Impressum (`context.imprint`) | 6 (`MAX_REQUESTS`) | – | 4 s (über `context.web`) |
| Förderkatalog (`context.foekat`) | Schnellsuche (ggf. erstes Namenswort, eingegrenzte Suche), je Abfrage max. 3 Ergebnisseiten (`MAX_ROWS`), dazu max. 3 Detailseiten (`MAX_DETAILS`) | 1 s | 20 s |
| Wayback CDX (`context.wayback`) | 7 | 1 s | 20 s |
| idw (`context.idw`) | 6, davon max. 5 Artikel | 1 s | 20 s |
| OpenAlex (`context.openalex`) | 2 je Gründer | 0,2 s | 15 s (`context.http.TIMEOUT`) |
| Google Patents (`context.patents`) | 6 je Lauf (`patents.MAX_REQUESTS`), nur `--patents` | 15 s | 20 s |
| Ollama (`context.ollama` Zitate, `context.classify`) | Zitate: 1 Anfrage, max. 8 Auszüge à 2.200 Zeichen; Klassifikation: Prompt max. 6.000 Zeichen (`MAX_PROMPT_CHARS`) | – | 30 s / 120 s |
