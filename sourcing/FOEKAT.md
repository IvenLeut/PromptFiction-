# Sourcing aus dem Förderkatalog des Bundes (EXIST)

Modul: `sourcing/foekat_export.py`, Einstieg `sourcing.engine.search(criteria)`, CLI `python -m sourcing foekat`.
Vorgehen nach [technologiestiftung/udb-foerderkatalog-scraper](https://github.com/technologiestiftung/udb-foerderkatalog-scraper)
(MIT-Lizenz, © 2026 Technologiestiftung Berlin). Der Code ist eine eigene Umsetzung und wurde nicht übernommen.

## Ablauf (live geprüft am 20.11.2026)

1. `GET https://foerderportal.bund.de/foekat/jsp/StartAction.do` setzt das Sitzungscookie JSESSIONID
   (`context.foekat.Session`: User-Agent `FounderRadar/1.0 …`, höchstens 1 Anfrage/s, Wiederholung bei 5xx).
2. `POST …/SucheAction.do` sendet das Formular (ISO-8859-15):
   `actionMode=searchlist`, `suche.detailSuche=true`, `suche.fkzSuche[0]=03EF%` bzw. `03EG%`,
   `suche.laufzeitVonSuche[0]=01.01.2024`, `suche.lfdVhb=N`, `suche.nurVerbund=N`, `suche.ZeSt=ZE`.
   Die Antwort ist eine HTML-Ergebnisseite mit `aria-label="Suchergebnis. 146 Treffer insgesamt. …"`.
3. `GET …/SucheAction.do?actionMode=print&presentationType=csv` liefert die vollständige Trefferliste der
   letzten Suche dieser Sitzung als `text/csv;charset=ISO-8859-15` (`Suchliste.csv`). Die Paginierung spielt dabei keine Rolle.

Bedeutung der Formularfelder laut Live-Formular und Probeabfragen:
- `lfdVhb` steht für „Nur lfd. Vorhaben“. `N` liefert auch abgeschlossene Projekte.
- `laufzeitVonSuche` filtert auf Projektbeginn ≥ Datum.
- `laufzeitBisSuche` filtert auf Projekt**ende** ≤ Datum. Die Abfrage 03EF%, von 01.01.2024 bis 31.12.2024 liefert deshalb 0 Treffer.

## Bereinigung

- Bytes werden als ISO-8859-15 dekodiert (0xA4 = €). Ein BOM wird entfernt.
- Zellen werden an `;` getrennt, aber nie innerhalb von `="…"`. Der Excel-Wrapper `="…"` wird entfernt.
  Beträge stehen ohne Wrapper in der Datei. Das leere Feld nach dem letzten `;` jeder Zeile entfällt.
- Gemeindekennziffer, Stadt/Gemeinde, Ort, Bundesland und Staat kommen doppelt vor. Sie heißen jetzt
  `… (Förderempfänger)` bzw. `… (Ausführende Stelle)`, je nachdem, hinter welcher Spalte sie stehen.
- Aus „Förder- / Auftragssumme (Anteil des Bundes) in EUR“ wird `Decimal` (`1.234.567,89` → `1234567.89`).
  Der Originaltext bleibt erhalten. Daten im Format `TT.MM.JJJJ` werden mit `context.foekat.parse_date` gelesen.
- Der Katalog ersetzt nicht darstellbare Zeichen durch `?` (z. B. „München ? Fakultät“). Diese Zeichen bleiben unverändert.

Spalten: FKZ, Ressort, Referat, Administrierende Stelle, Arb.-Einh., Förderempfänger /Auftragnehmer,
5 × Geo, Ausführende Stelle, 5 × Geo, Thema des geförderten Vorhabens, Leistungsplansystematik, Klartext
Leistungsplansystematik, Laufzeit von, Laufzeit bis, Förder-/Auftragssumme, Förderprofil, Projekt, Förderart.

## Trefferzahl-Prüfung und Fallback

Pro Präfix wird die Zahl der eindeutigen FKZ im Export mit der Trefferzahl des Servers verglichen.
Ein Fallback greift bei Abweichung oder wenn der Export die Transportgrenze von 3 MB übersteigt.
Dann wird die Abfrage nach dem nächsten FKZ-Zeichen aufgeteilt (`03EF` → `03EF0…9`, `03EFA…Z`),
höchstens 2 Ebenen tief. Die Teile werden über das FKZ dedupliziert. Teilabfragen mit 0 Treffern brauchen keinen Export.

Abweichung vom Scraper: Der Scraper teilt nach Jahr mit `von=01.01.J` und `bis=31.12.J`. Wegen der
Semantik von `bis` (Projektende) findet diese Aufteilung nur Projekte, die im selben Jahr beginnen und
enden. Mehrjährige EXIST-Projekte gingen dabei verloren. Ein FKZ-Präfix teilt die Menge dagegen
lückenlos auf.

Lässt sich eine Abweichung nicht beheben, gelten folgende Regeln:
- Es werden nur Zeilen validierter Teilabfragen zurückgegeben.
- `ExportResult.complete=False` wird gesetzt und `warnings` erklärt die Lücke.
- Die CLI endet mit Exit-Code 1.

Diese Fehler führen zum Abbruch:
- `ExportNetworkError` bei einem Netzfehler.
- `NotCsvError`, wenn der Server HTML statt CSV liefert (z. B. nach Sitzungsverlust).
- `EmptyExportError`, wenn der Export trotz Treffern leer ist.
- `ResultPageError`, wenn die Ergebnisseite keine Trefferzahl enthält.

Diese Ergebnisse werden nicht gecacht. `engine.search` wandelt sie in `SourcingError` um.

## Lead-Regeln

- **Projekt/Verbund:** Zeilen gehören zum selben Lead, wenn sie denselben nicht leeren Wert in der Spalte
  „Projekt“ haben. Das gilt auch, wenn sich ihre FKZ nur durch einen Endbuchstaben unterscheiden
  (`…0063A`/`…0063B`). Gleiche Namen allein führen bewusst nicht zur Zusammenlegung (Leonards Regel).
  Jede FKZ wird ein eigenes Signal. In den Daten ab 2024 gibt es keinen Verbund (Spalte „Projekt“ immer leer).
  Aus 733 Zeilen werden deshalb 733 Leads.
- **id:** `foekat-` + FKZ in Kleinbuchstaben (bei Verbund der FKZ-Stamm), z. B. `foekat-03efbb0063`.
- **name:** Das Thema ohne Präfix wie „EXIST-Forschungstransfer:“, „EXIST - Forschungstransfer:“ oder
  „EFT-Forschungstransfer:“. Ein früherer Name wie „(ehemals X)“, „(ehem. X)“ oder „ehemals X“ wird
  abgetrennt und in `description` erwähnt. Bei sehr langen alten Themen gilt der Teil vor „ - “.
  Der Name ist immer ein Teilstring des Themas. Ab 2024 ist das Thema fast immer ein Kurzname
  („HoCHQuant“, „u/press (ehemals trykk)“).
- **country="DE"** setzen wir nur, wenn die Zeile als Staat des Förderempfängers oder der
  Ausführenden Stelle „Deutschland“ nennt. `country_evidence.url` ist die Detail-URL
  `context.foekat.detail_url(fkz)`. Die `finding` zitiert Name, Ort, Bundesland und Staat beider Stellen.
  `retrieved_at` ist der Abrufzeitpunkt des gecachten Exports.
- **location:** Ort der Ausführenden Stelle. Fehlt er, gilt der Ort des Förderempfängers.
- `source_url` ist die Detail-URL, `source_name` „Förderkatalog des Bundes“ und `is_demo` False.
  `founders=[]`, `contact_email`, `website`, `has_vc`, `founding_year` und `founding_month` bleiben leer
  bzw. None. Der Projektbeginn ist kein Gründungsdatum.
- **signals:** Ein Signal pro FKZ mit `source="Förderkatalog"`, `type="exist_projekt"`, `url`=Detail-URL
  und `date`=Projektbeginn. Die `evidence` beginnt mit `FKZ <fkz>;` und nennt danach Programm, Thema,
  Förderempfänger, Ausführende Stelle, Laufzeit, Summe (`876.964,00 €`), Leistungsplansystematik,
  Ressort und Förderart. Alle Werte stehen wörtlich so im Katalog. Schritt 2 findet die FKZ über seine
  Regex (`context/engine.py`) und fragt sie exakt ab. Der Typ `exist_projekt` steht in Schritt 2 auf der
  Liste `NO_QUOTE_TYPES`. Katalogzeilen gehen deshalb nicht als Firmenaussage in Klassifikation oder
  Ollama-Zitate ein.
- **prioritization_reason:** `"<Programm> seit <Beginn>, <Summe>. Branche … per Regel … (Feld: „Text“, Treffer: …). Flags: …"`.

## Branchen- und Sektorzuordnung

Die Regeln prüfen Schlüsselwörter auf Deutsch und Englisch, ohne Groß- und Kleinschreibung.
Ein Wort in `<…>` zählt nur als ganzes Token (CamelCase wird getrennt: „SherpAI“ → sherp, ai).

1. Die Felder werden in dieser Reihenfolge geprüft: **Thema**, **Ausführende Stelle**, **Förderempfänger**.
   Das erste Feld mit mindestens einem Treffer entscheidet.
2. Innerhalb dieses Felds gewinnt die Regel mit den meisten Treffern.
3. Bei Gleichstand gilt die Reihenfolge der Tabelle.

Leistungsplansystematik, Förderprofil und Förderart sind bei allen Zeilen gleich (RB0570 EXIST) und unterscheiden die Branchen nicht.

| Regel | Industry | htgf_sector | Beispiele für Schlüsselwörter |
| --- | --- | --- | --- |
| health | HealthTech | life_sciences | medizin, klinik, charité, pharma, gesundheit, biolog, immun, therap, diagnost, neuro |
| climate | ClimateTech | climate_tech | energie/energy, klima/climate, solar, wasserstoff, batter, umwelt, recycling, agrar |
| fintech | FinTech | digital_tech | finanz, fintech, `<bank>`, versicherung, payment, blockchain, krypto, wallet |
| chemistry_materials | Industrial / DeepTech | chemie_materialien | chemie, werkstoff, material, polymer, kunststoff, katalys, keramik |
| industrial_deeptech | Industrial / DeepTech | industrial_deep_tech | maschinen, ingenieur, produktion, robot, elektrotechnik, photon, laser, physik, quanten, sensor |
| software_ai | AI / Software | digital_tech | informatik, software, `<ki>`, `<ai>`, data science, daten, digital, cyber, `<xr>` |

Trifft keine Regel, gilt ein Standardwert je Programm. Der Lead bekommt dann das Flag
`industry_unclassified` und `htgf_sector=None`.
- 03EF wird Industrial / DeepTech, weil Forschungstransfer forschungsbasierte Entwicklungsvorhaben fördert.
- 03EG wird AI / Software.

Für jede Zuordnung stehen Regel, Feld, zitierter Text und Treffer in `prioritization_reason`.

Stand der Live-Daten vom 20.11.2026 (733 Leads):

| Branche | Leads | davon Standardwert |
| --- | --- | --- |
| AI / Software | 441 | 309 |
| Industrial / DeepTech | 186 | 23 |
| HealthTech | 70 | 0 |
| ClimateTech | 34 | 0 |
| FinTech | 2 | 0 |
| **Summe** | **733** | **332** |

Viele 03EG-Zeilen nennen nur die Hochschule.

## Bezug zu Leonards Kriterien (sourcing/AGENTS.md)

EXIST-Projekte sind **frühe Signale**. Meist handelt es sich um Teams vor der Gründung. Zuwendungsempfänger
ist die Hochschule oder das Institut, nicht die Firma. Nach Leonards Regeln sind sie deshalb **interne
Prüffälle** und keine fertigen Zeilen der UI-Liste. Gründer:innen, E-Mail, Website und Gründungsmonat
fehlen. Der Katalog belegt den Sitz der Hochschule, nicht den Sitz einer Firma.

Maschinenlesbare Kennzeichen in `prioritization_reason` nach `Flags:`:

| Flag | Bedeutung |
| --- | --- |
| `early_signal_exist` | Lead stammt aus einem EXIST-Projekt |
| `founding_date_unknown` | Gründungsdatum unbekannt |
| `founders_unknown` | Gründer:innen unbekannt |
| `pre_founding_team` | Team vor der Gründung |
| `internal_review_case` | interner Prüffall |
| `recipient_company` | Empfänger ist eine Firma, statt `pre_founding_team` gesetzt |
| `exist_ft_phase2_candidate` | 03EF-Zeile, deren Empfänger eine Rechtsform wie GmbH/UG/AG trägt (nicht gGmbH) und weder Empfänger noch Ausführende Stelle akademisch klingen |
| `industry_unclassified` | keine Branchenregel traf, Standardwert gesetzt |
| `verbund` | Projekt mit mehreren FKZ |
| `project_finished` | Projektende liegt vor dem Abrufdatum |
| `executing_country_unassigned` | Staat der Ausführenden Stelle „nicht zuzuordnen“ (1 Fall) |

`exist_ft_phase2_candidate` gibt es in den Daten ab 2024 nicht. Historisch kommt das Muster bei FKZ
03EFU* vor (z. B. „The Captury GmbH“, 2014). Auch dann wird kein Gründungsdatum gesetzt.
Erst Schritt 2 (Impressum, Register) kann eine Firma belegen.

`sourcing.engine.search` liefert die Leads trotzdem an die Pipeline. Für die UI-Liste nach Leonards
Kriterien müssen sie vorher gefiltert oder angereichert werden. Das ist noch offen.

## Datenschutz

Wir verwenden nur öffentliche Katalogdaten. Gründer:innen, E-Mail-Adressen und Telefonnummern werden
weder abgeleitet noch gespeichert. Die Bezeichnung der Ausführenden Stelle enthält teils Namen von
Professor:innen, z. B. „AG Sophie van Linthout“. Sie bleibt als institutionelle Angabe wörtlich erhalten
und wird nie als Gründer:in übernommen. Die Fixtures enthalten nur Katalogzeilen.

## Determinismus und Cache

Jedes Paar aus Suche und Export liegt als ein Eintrag in `context.cache.Cache` (`.cache/context.db`, TTL 14 Tage):
- Schlüssel: `foekat-export:v1:` + sha1 des Formulars.
- Inhalt: Trefferzahl, Roh-CSV (base64) und Abrufzeit.

Die Abrufzeit füllt `Evidence.retrieved_at`. `evidence_id` wird aus URL, Feld, Aussage und Datum berechnet.
Mit gefülltem Cache ergeben zwei Läufe byte-identische Shortlist- und Statistikdateien und brauchen keine
Netzanfrage. Die Sortierung ist: neuester Projektbeginn zuerst, dann id. Nach Ablauf der TTL holt ein Lauf
neue Daten.

## Bekannte Grenzen

- Die Branchenzuordnung beruht nur auf Schlüsselwörtern. 45 % der Leads erhalten den Standardwert.
- `pipeline.discover` bricht bei `SearchCriteria.limit` ab (höchstens 200).
- Gruppierung zu Verbünden ist nur an konstruierten Fällen getestet, weil die Daten ab 2024 keinen Verbund enthalten.
- Der Fallback ist auf Tiefe 2 begrenzt.
- Ändert der Katalog sein Formular oder Exportformat, entstehen `ResultPageError` bzw. `NotCsvError`.
  Es gibt dann keinen stillen Fallback.
