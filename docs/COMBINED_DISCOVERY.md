# Gemeinsame Suche, Kontext und Bewertung

Basis ist `chore/repo-cleanup` bei `fda6207`, zusammengeführt mit dem bestehenden
Investment-Cockpit und der lokalen Open-Data-Suche. Der Standard benötigt keinen
KI-Schlüssel. Die Suche wählt Unternehmen automatisch aus.

## Was der Cleanup-Branch mitbringt

* `sourcing/foekat_export.py`: EXIST-Forschungstransfer und Gründungsstipendium aus
  dem Bundes-Förderkatalog, CSV-Validierung, Cache, Anfragebudget und Warnungen bei
  unvollständigen Exporten.
* `sourcing/mapping.py`: Projektgruppen, Branchenbegriffe, Herkunft der Zuordnung
  und deterministische Suchpriorität. Diese Priorität ist kein Investmentscore.
* `context/`: belegte Fakten, Fördermittel, Impressum, Forschungs- und weitere
  Quellen. Fördermittel werden nicht als VC-Runde behandelt.
* `scoring_input.py` / `scoring_market.py`: nachvollziehbare Parameter einschließlich
  Marktberechnungen, Quellenreferenzen, fehlender/widersprüchlicher Werte und Stichtag.
* `evaluation/engine.py` / `scoring/`: regelbasierte Bewertung und Hypothesentexte.
  Die Scoring-CLI akzeptiert jetzt auch einen `ContextResult` direkt.

## Ablauf und Abgrenzungen

1. Die bestehenden Collector-CLIs erzeugen getrennte, gespeicherte Quellenstände.
2. `python -m sourcing.combined` liest `qualified.json` und den Förderkatalog-Export.
   Es gibt dabei weder Netz- noch Modellaufrufe. Alle fünf Branchen werden erhalten.
3. Ein `DiscoverySnapshot` hält beide Pools, Herkunft, Quellenhashes, Datenlücken,
   exakte Datumsentscheidung und Mehrfachbranchenzuordnung. Automatisch vereinigt
   werden nur gleiche explizite LEIs. Namensähnlichkeit, dieselbe Hochschule oder
   ein gemeinsamer Ort reichen nicht. Noch unerkannte Beziehungen bleiben getrennt.
4. `batch_analysis.run_snapshot()` übergibt passende `RawLead`s an die unveränderte
   Schrittfolge `collect_context → build_scoring_input → evaluate_context`.
   `scoring_market.market_parameters` bleibt Teil dieser Parameterberechnung.
5. Pro Branche entsteht ein `AnalysisRun`. Unter `evaluation_v2` bleiben Teilwerte,
   Belege, Ausschlüsse und fehlende Kriterien vollständig erhalten. `discovery`
   enthält den Suchlauf und die Kriterien; beide Bereiche sind getrennt.
6. Das Cockpit kann gespeicherte `AnalysisRun`s direkt lesen. Ein Seitenwechsel
   startet damit keine neue Recherche und keine Modellabfrage.

Standardkohorte `companies`: Deutschland-Beleg, identitätsgeprüfte Website mit
technischer Eigendarstellung, genaues Gründungsdatum innerhalb der letzten zwei
Kalenderjahre bis zum expliziten Stichtag, keine bekannten Alterswidersprüche.
Die Intervallgrenzen sind inklusive; am 21.11.2026 gilt 21.11.2024–21.11.2026.
GLEIF `entity.creationDate` beschreibt die juristische Einheit. Ein älteres
fortgeführtes Geschäft ist dadurch nicht ausgeschlossen. Innovation bleibt eine
belegte Eigendarstellung, keine unabhängige technische Prüfung.

`research` enthält fachlich zugeordnete Recherchefälle, etwa EXIST-Projekte ohne
belegte Firmengründung. Nur der Projekttitel zählt als Branchenbeleg. Ein Institut
oder ein Programmstandard allein reicht nicht; solche Datensätze bleiben im
Snapshot zur Prüfung erhalten, werden aber keiner fachlichen Longlist zugeschlagen.
`all` umfasst beide zugeordneten Kohorten, keine nachweislich zu alten Firmen.

Die Filter ersetzen weder einen vollständigen Handelsregisterexport noch eine
Finanzierungsprüfung. GLEIF ist unvollständig; EXIST erfasst nur geförderte Vorhaben.
733 Förderprojekte sind **keine 733 nachgewiesenen jungen Unternehmen**.

## Reproduzierbar ausführen

Im Repository, mit aktivierter Python-Umgebung:

```powershell
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-discovery.txt

# Zweite Quelle frisch abrufen; Projektbeginn ist ein Suchfilter, keine Gründung.
python -m sourcing foekat --since 2024-11-21 --as-of 2026-11-21 --out data/foekat.json --stats data/foekat-stats.json

# Die Open-Data-Collector-Aufrufe stehen in OPEN_DATA_DISCOVERY.md.
python -m sourcing.combined --open-data data/open-discovery/export --foekat data/foekat.json --foekat-stats data/foekat-stats.json --as-of 2026-11-21 --out data/combined-discovery.json

# Standard: gespeicherte Belege, kein Internet, keine KI, maximal 200 je Branche.
python -m batch_analysis --snapshot data/combined-discovery.json --context light --out data/analysis

# Recherchepool separat auswerten; kein Vermischen mit der Firmenkohorte.
python -m batch_analysis --cohort research --context light --out data/analysis-research

$env:FOUNDERRADAR_MODE = 'live'
$env:FOUNDERRADAR_ANALYSIS_DIR = 'data/analysis'
python -m streamlit run cockpit.py
```

`data/` wird nicht in Git eingecheckt. Vor dem ersten Förderkatalog-Aufruf `data/`
anlegen, falls es noch nicht existiert. Ein vorhandener Beispielexport lässt sich
mit `--foekat examples/sourcing/shortlist.json` ohne Netz kombinieren. Für diesen
alten Export ist die Vollständigkeit nicht separat dokumentiert; das Tool setzt
sie deshalb auf unbekannt. Die Quellenstände und der Stichtag werden offengelegt.

Die Suchentscheidung und Scores sind mit denselben Eingaben/Stichtagen wiederholbar.
Zeitstempel der Ausführung sind Metadaten, kein Bestandteil der Bewertung.
Die Collector-Datenbasis muss für neue Gründungen ebenfalls aktualisiert werden;
ein neuer Stichtag allein findet keine neuen Firmen.

## KI und spätere Kontextrecherche

Standard: alles Code. Suche, Auswahl, Altersprüfung, Branchenregeln, Identitäten,
Parameter, Gewichte, Ranking und Hypothesen laufen deterministisch. Schritt 1
erzeugt keine Risiko-, Markt- oder Unternehmensbewertung und keine Investmentthese.

`batch_analysis --context live` aktiviert die vorhandenen öffentlichen Quellenabfragen,
aber weiterhin kein Modell. Das kann für viele Firmen lange dauern. Für die Demo
ist ein gespeicherter Lauf geeignet. Zusätzliche Kontextarbeit lässt sich auch
über `python -m context` gezielt pro Lead erledigen und lokal nachbewerten.

Qwen ist optional über den vorhandenen Ollama-Adapter erreichbar:
`FOUNDERRADAR_CONTEXT_MODE=live` und `FOUNDERRADAR_OLLAMA_MODEL=<installierter Name>`.
Den gespeicherten Analysemode dafür mit `Remove-Item Env:FOUNDERRADAR_ANALYSIS_DIR`
abschalten. Der vorhandene Adapter spricht `127.0.0.1:11434/api/chat`; kein API-Key
ist nötig. Er wählt Zitate/Klassifikationen im Kontextschritt, berechnet keine Scores.
Temperatur 0 ersetzt keine Reproduzierbarkeitsgarantie; Antworten werden validiert
und gecacht. Ein anderer, etwa OpenAI-kompatibler Endpunkt ist noch nicht integriert.

## Fachliche Abweichungen und verbleibende Arbeit

* Die Suche des Kollegen findet auch Vorgründungsteams und ältere Projekte.
  Die neue Kohortentrennung verhindert, dass sie die Zwei-Jahres-Firmenzahl erhöhen.
* Ein schwaches Institutsschlagwort wird nicht als Produktbranche übernommen.
* Fehlende Kriterien erhalten im vorhandenen Scorer teilweise neutrale 50 Punkte.
  Die Formel bleibt unverändert. Confidence und unbelegte Teilwerte müssen sichtbar
  sein; bei mehreren realen Firmen beträgt die Confidence nur etwa 3 Prozent.
  Ein rechnerischer Score ist dann kein belastbares Investmenturteil.
* `company_score` bezeichnet in dieser Engine den Team-Score, nicht die gesamte
  Unternehmensqualität. Die fachliche Bezeichnung im Cockpit muss das wiedergeben.
* Fehlende VC-Belege sind kein Beleg für fehlende Finanzierung. Unbekannt bleibt
  unbekannt; bestätigtes oder widersprüchliches VC-Funding wird zurückgehalten.
* `first_signal_date` gehört in Schritt 2; die einzelnen datierten Quellen sind
  schon in Schritt 1 verfügbar. Eingabefelder bleiben bei der Anreicherung unverändert.
* Das GLEIF-Datum wird ausdrücklich als Gründungsereignis transportiert, nicht als
  Veröffentlichungs- oder Abrufdatum. Produktzitate verweisen auf ihre Website,
  nicht auf die GLEIF-Identitätsquelle.
* Nächste Datenausbaustufe: EXIST-Projekte mit juristischen Firmen/Impressen verbinden,
  Gründungsdatum absichern und dann erst in die Firmenkohorte aufnehmen. Aktuell
  ist kein automatischer Suchmaschinenabgleich Projektname → Firmenwebsite eingebaut.
* Für ein belastbares Management-Cockpit fehlen weiterhin ausreichende Team-,
  Markt-, Umsatz-, Kunden- und IP-Belege sowie mehr qualifizierte Treffer. Der
  Datenvertrag, Offline-Handoff und vorhandene Analystenentscheidungen sind nutzbar.

Es wurden für die Integrationsprüfung keine externen KI-Dienste aufgerufen.
