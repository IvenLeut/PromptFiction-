# FounderRadar: Open-Data-Discovery

Ziel: bis zu **200 Firmen je Branche**, Deutschland, **20.11.2024–20.11.2026**. Keine KI-Aufrufe, keine bezahlte Firmen-API, keine Accelerator-/VC-Portfolios und keine Demo-Unternehmen. Das Mengenlimit ist eine Kapazität, keine Zusage über die Zahl nachweisbarer Treffer.

## Datenwege

1. **GLEIF**: deutsche Rechtsträger nach `entity.creationDate`. Das LEI-Ausgabedatum wird ausdrücklich nicht als Gründung verwendet. Abfragen werden wegen des 10.000-Treffer-Limits nach Zeitfenstern geteilt. Die Tagesgrenzen werden lokal nochmals geprüft. LEI-Daten decken nicht alle deutschen Unternehmen ab; eine neue juristische Einheit kann ein älteres Geschäft fortsetzen.
2. **CORDIS**: kompletter Horizon-Europe-Export, deutsche private KMU mit Forschungsprojekten. Projektstart ist niemals Gründungsdatum. Ein Konsortialprojekt beweist nicht, dass sämtliche darin beschriebenen Technologien Produkte jedes beteiligten Unternehmens sind.
3. **Common Crawl**: öffentlicher `cluster.idx`, deterministisch ausgewählte deutsche Indexblöcke, archivierte Impressen über HTTP-Byte-Ranges. Funktioniert ohne CDX-Suchserver, API-Schlüssel oder AWS-Konto. Das ist eine Stichprobe, kein vollständiger Deutschlandscan.
4. **Firmenwebsites**: identitätsgeprüfte Impressen und wenige Produkt-/Unternehmensseiten. Domainvorschläge aus Firmennamen sind nur Suchversuche; die Domain wird erst nach Abgleich des vollständigen Firmennamens und Registernummer oder PLZ plus Ort übernommen.

## Ausführen

```powershell
python -m pip install -r requirements.txt
python -m free_discovery.collect download --work data/open-discovery
python -m free_discovery.collect run --work data/open-discovery --out data/open-discovery/export --max-companies 2000 --target 200 --workers 6
python -m free_discovery.collect recheck --work data/open-discovery --out data/open-discovery/export
python -m free_discovery.archive_index --root data/commoncrawl --blocks 64 --documents 150
python -m free_discovery.collect run --work data/open-discovery --out data/open-discovery/export --max-companies 2000 --archive-imprints data/commoncrawl/CC-MAIN-2026-43/imprints.json
```

Im FounderRadar-Repository die zusätzlichen Collector-Abhängigkeiten mit `python -m pip install -r requirements-discovery.txt` installieren. Im eigenständigen Paket heißt diese Datei `requirements.txt`. Der Live-Adapter selbst hat keine zusätzlichen Abhängigkeiten.

Das Archivmodul übergibt nur auslesbare juristische Firmenidentitäten an die Recherche. Mehrdeutige Impressen bleiben im Audit. Ein Archivzeitstempel wird niemals als Gründungsdatum genutzt. `supplemental_sources.json` dokumentiert eine zusätzliche Unternehmensseite aus der Qualitätsprüfung; Wiederholung mit `collect recheck --supplemental-sources supplemental_sources.json`. Diese Datei liefert keine manuell ausgewählten Firmen, sondern einen Gegenbeleg zum Alter eines bereits automatisch gefundenen Rechtsträgers.

Im integrierten Repository heißt diese Belegdatei `discovery-supplemental-sources.json`. Ein `recheck` speichert die aktualisierten Belege auch in den Firmen-Checkpoints. Beim Wiederaufnehmen werden die gespeicherten Seiten mit den aktuellen Regeln erneut beurteilt.

`quality_holds.json` dokumentiert einen belegten Alterswiderspruch aus der Qualitätsprüfung, dessen historische Seite live inzwischen verändert wurde. `collect recheck --quality-holds quality_holds.json` stellt ausschließlich bereits gefundene IDs zurück; damit lassen sich keine Firmen aufnehmen oder Altersnachweise erfinden. Im Repository heißt die Datei `discovery-quality-holds.json`. Gespeicherte Sperrvermerke bleiben bei weiteren Batches erhalten.

Mit `--include-unmatched-names` werden auch GLEIF-Namen ohne Technologiebegriffe recherchiert. Der Standard priorisiert Technologiebegriffe und CORDIS-Beteiligungen; dadurch werden neutral benannte Unternehmen zunächst unterrepräsentiert. `--max-companies` begrenzt **Rechercheversuche**, nicht Treffer. Größere Werte erhöhen Arbeit und Laufzeit, nicht automatisch die Qualität.

Für einen vorhandenen Recherchebestand erweitert der neue inkrementelle Lauf die Suche ohne Branchenwort im Firmennamen:

```powershell
python -m free_discovery.expand plan --work data/open-discovery --new-companies 1000
python -m free_discovery.expand run --work data/open-discovery --out data/open-discovery/export --new-companies 1000 --refresh-matched --max-domains 6 --max-extra-pages 4
```

`expand` benötigt `all_entities.json`, `results.json` und `discovery_manifest.json` aus einem bisherigen Collector-Lauf. Es recherchiert zusätzliche IDs, erhält die bisherigen Ergebnisse und fügt die neuen hinzu. Der nächste Aufruf nimmt den nächsten bisher nicht recherchierten Teilbestand. Die Reihenfolge bevorzugt anhand des Namens erkennbare Kapitalgesellschaften ohne Verwaltungsbegriffe und verwendet dann einen festen Hash. Das ist eine Recherchepriorität, kein Beleg operativer Tätigkeit. Die Aufnahmefilter für Alter, Identität und Technik gelten weiterhin. `--refresh-matched` prüft bereits gespeicherte Webseiten mit der verbesserten HTML-Textauslesung erneut. Abgebrochene Recherchen werden über Checkpoints fortgesetzt. Der bisherige Stichtag wird aus dem Manifest übernommen.

Ist eine Ergebnisdatei beispielsweise durch Excel gesperrt, bleiben die Rechercheergebnisse unter `--work` erhalten. Nach Freigabe der Datei kann `python -m free_discovery.collect export --work data/open-discovery --out data/open-discovery/export --start 2024-11-20 --end 2026-11-20` den Export erneut erzeugen; alternativ ein neues Ausgabeverzeichnis verwenden. Die Daten des Befehls müssen zum Manifest passen.

Die verbesserte Domain-Suche berücksichtigt auch Bindestrichvarianten und `.io`. Zusammenhängender Text bleibt trotz HTML-Hervorhebungen erhalten. URL-Fragmente führen nicht zu mehrfachen Abrufen derselben Unterseite. `results/expansion_report.json` protokolliert den zusätzlichen Rechercheumfang und neu aufgenommene bzw. entfernte Kandidaten.

`--start` und `--end` sind explizite Stichtage, nicht die Uhr des ausführenden Rechners. Neue Läufe mit neuen Stichtagen bekommen andere Firmen-Checkpoints. Einen neuen HTTP-Quellenstand in einem neuen `--work`-Verzeichnis sammeln. `--offline` verwendet ausschließlich vorhandene HTTP-Snapshots.

## Qualitätsgrenzen

- `qualified_candidate`: deutscher Länderbeleg, identitätsgeprüfte Website, passendes GLEIF-Entstehungsdatum oder eindeutiges zulässiges Gründungsjahr, technologische Eigendarstellung. Das ist ein Recherchekandidat, keine unabhängig bestätigte Innovation oder Finanzierungsreife.
- `review_required`: mindestens eine Voraussetzung fehlt oder widerspricht einer anderen Quelle. Diese Firmen werden **nicht** automatisch ins Dashboard als qualifizierte Treffer geladen.
- Gründungsjahre an den Grenzen 2024 und 2026 ohne genaues Datum bleiben bei einer rein jahresgenauen Website-Angabe unklar. 2025 ist vollständig im Fenster.
- Eigenangaben zu Entwicklung/Technologie sind Hinweise, keine Patent-, Produkt- oder Marktvalidierung. Automatische Begriffsregeln können Fehlzuordnungen erzeugen. Das Ergebnis benötigt fachliche Prüfung.
- Nicht gefunden bedeutet nicht nicht existent. Kein Treffer beweist keine fehlende VC-Finanzierung; `has_vc` bleibt unbekannt.
- GLEIF-Namen und Rechtsformwechsel, Namensänderungen, Unternehmensgruppen, historische Domains und mehrsprachige Websites sind Grenzen der Zuordnung.
- Eine ausdrücklich abweichende Registernummer wird auch bei gleicher Adresse zurückgestellt. Hinweise auf mehr als zwei Jahre Geschäftstätigkeit werden getrennt von Berufserfahrung der Gründer geprüft. Reine Büroautomatisierung wird nicht allein deswegen als Industrial / DeepTech eingeordnet.
- Kein Score wird aus bloßen Keywordtreffern erfunden. Score, Marktpotenzialscore, Unternehmensscore und Investmenthypothese bleiben bis zur vorhandenen Kontext-/Scoring-Stufe leer. Risiko und Stage bleiben unbewertet beziehungsweise unbekannt.
- Die Archive werden nicht an KI-Dienste übergeben. Urheberrechtliche und robots-bezogene Quellenvorgaben bleiben zu berücksichtigen; öffentliche Erreichbarkeit ist keine pauschale Weiterveröffentlichungserlaubnis. Öffentlich ausgeliefert werden Identitäten, kurze Belege und Quellenverweise, keine kompletten Webkopien.

## Ergebnisse

`results/qualified.json`: eindeutige qualifizierte Kandidaten mit Belegen und Branchen.

`results/review_queue.json`: getrennte Recherchefälle; keine als jung behaupteten Unternehmen ohne Nachweis.

`results/raw_leads.json`: deduplizierter FounderRadar-`RawLead`-Export. Eine Primärbranche je Datensatz; alle Branchen stehen in `qualified.json`. Die Branchenexporte erlauben Mehrfachzuordnung derselben Firma, enthalten aber innerhalb einer Branche keine Dubletten.

`results/AI_Software.json`, `ClimateTech.json`, `HealthTech.json`, `FinTech.json`, `Industrial_DeepTech.json`: maximal 200 `RawLead`-Datensätze je Branche.

`results/longlist.csv`: genau die sieben vereinbarten Bewertungsspalten. Die Firmenidentität liegt in `row_map.json`; diese Dateien gemeinsam verwenden und die CSV nicht unabhängig sortieren. Im Dashboard steht die Firmenidentität bereits im vorhandenen Lead-Modell.

`results/longlist.json`: dieselben sieben Spalten unter `columns`, daneben stabile ID, Name, Branchen, Quellenverweis und Datumsbasis. Für eigene Integrationen dieses Format verwenden; die Firmenzuordnung bleibt beim Sortieren erhalten.

`results/report.json`: tatsächlich erreichte Zahlen, offene Lücke zum Ziel, Quellen-/Bewertungsgrenzen. **Die Menge darf nicht durch Vermutungen, alte Firmen oder Demo-Daten aufgefüllt werden.**

`results/discovery_manifest.json`: Zahl der Ausgangsdatensätze und tatsächlich eingeplanten Recherchen. Die geprüfte Menge ist ausdrücklich keine Menge bestätigter junger Startups. Gründungsdaten, technische Eigendarstellung und Unterlagen zum ursprünglichen Geschäft müssen getrennt betrachtet werden.

Die HTTP-Snapshots, GLEIF-Rohdaten und CORDIS-Datei liegen unter `--work`; Ergebnisse und individuelle Fehlversuche werden gespeichert. Wiederholungen setzen über Checkpoints fort. Fehlerhafte HTTP-Aufrufe sind im Snapshot ebenfalls gespeichert, damit kein wiederholtes Hämmern auf einen Server entsteht. Für erneute Prüfung einer zeitweiligen Störung neuen Quellenstand anlegen.

## Integration in IvenLeut/PromptFiction-

Der Collector bleibt als eigene Suchquelle erhalten. Der kombinierte Adapter steht in `sourcing/combined.py`, der reine Open-Data-Adapter in `sourcing/open_data.py`. `sourcing/engine.py` bleibt die Förderkatalog-Implementierung und darf nicht ersetzt werden. Die gemeinsame Einrichtung steht in [COMBINED_DISCOVERY.md](COMBINED_DISCOVERY.md).

Die lokale Integration erfolgt durch `python apply_local_integration.py "C:\Pfad\zu\PromptFiction-"`. Das Skript prüft die bekannten Platzhalter vor Änderungen und erzeugt keinen Commit oder Push. Ein reiner Code-Import ohne Ergebnisdateien ist mit `--skip-data` möglich. Danach liegen die Ergebnisse im bestehenden, Git-ignorierten `data/open-discovery/export`.

```powershell
$env:FOUNDERRADAR_DISCOVERY_DIR = 'C:\Pfad\zu\results'
$env:FOUNDERRADAR_MODE = 'live'
$env:FOUNDERRADAR_SOURCING = 'open_data' # nur dieser einzelne Suchweg
.\.venv\Scripts\python.exe -m streamlit run cockpit.py
```

Sourcing liest ausschließlich qualifizierte Branchendateien. Die bestehenden Kontext- und Evaluationsmodule bleiben erhalten. Ein langlaufender Crawl wird nicht durch einen Dashboard-Klick gestartet. Fehlende Dateien lösen einen klaren Fehler aus, leere echte Ergebnisse bleiben leer; kein Demo-Fallback. Ein API-Key ist für diesen Collector nicht nötig.

Das Cockpit fordert im Live-Modus jetzt standardmäßig bis zu 200 Firmen je Branche an. `FOUNDERRADAR_DISCOVERY_LIMIT` kann diesen Wert innerhalb des bestehenden Vertrags (1–200) überschreiben; im Demo-Modus bleibt der Standard 30. Dies ist ein Abruflimit, keine Zusage über vorhandene Treffer.

Tests: `python -m unittest test_discovery` im eigenständigen Paket. Im FounderRadar-Repository: `python -m pytest tests/test_free_discovery.py tests/test_sourcing_open_data.py tests/test_pipeline.py`. Tests verwenden synthetische Fixtures, die nicht in den Forschungsdaten oder Exporten enthalten sind.

## Quellen und Reproduzierbarkeit

- GLEIF: https://api.gleif.org/api/v1/lei-records ; https://www.gleif.org/en/lei-data/gleif-api/
- CORDIS: https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip ; https://cordis.europa.eu/projects
- Common Crawl: https://data.commoncrawl.org/cc-index/collections/CC-MAIN-2026-43/indexes/cluster.idx ; https://www.commoncrawl.org/get-started

GLEIF und CORDIS liefern strukturiertes Ausgangsmaterial, Webseiten liefern Eigendarstellungen. Im Ergebnis wird die Herkunft separat erhalten. HTTP-Dokumente bekommen einen SHA-256-Hash; WARC-Dokumente sind durch Crawl, Datei, Byteoffset und Länge reproduzierbar referenziert. Das Netz ist veränderlich; identische Resultate werden nur für eingefrorene Snapshots und dieselbe Codeversion erwartet.
