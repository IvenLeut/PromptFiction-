# Sourcing aus dem Förderkatalog des Bundes (EXIST)

Übergabe für Sourcing und Scoring, Stand 20.11.2026, geprüft gegen Code und Cache-Lauf.
Code: `sourcing/foekat_export.py` (Abruf, Prüfung, Bereinigung), `sourcing/mapping.py` (Zeilen → `RawLead`,
Branche, Priorität), `sourcing/engine.py` (`search`), `sourcing/__main__.py` (CLI).

## Was die Quelle ist und warum sie früh ist

Der [Förderkatalog](https://foerderportal.bund.de/foekat/) listet geförderte Vorhaben des Bundes. Wir lesen
zwei EXIST-Programme mit Projektbeginn ab 01.01.2024, laufend und abgeschlossen: `03EF*`
EXIST-Forschungstransfer (Laufzeit meist 18–24 Monate, 146 Leads am 20.11.2026) und `03EG*`
EXIST-Gründungsstipendium (fast immer 12 Monate, 587 Leads).
Ein EXIST-Team gründet in der Regel während oder am Ende der Förderung, der Projektbeginn liegt also meist
12 bis 24 Monate vor der Gründung (Erfahrungswert, der Katalog belegt ihn nicht). Das Team taucht im Katalog
auf, bevor es Firma, Website oder Presse gibt. Nach den Sourcing-Regeln des Teams sind diese Funde **frühe Signale**
und **interne Prüffälle**, keine Zeilen der UI-Ergebnisliste.

## Von null bis zu Scores (getestet 20.11.2026)

~~~powershell
# Schritt 1: Fundliste (alle 733 Leads; mit gefülltem Cache ohne Netz, byte-identisch zum Beispiel)
python -m sourcing foekat --since 2024-01-01 --out shortlist.json --stats stats.json
# nur Priorität >= 80: 54 Leads, alle 03EF
python -m sourcing foekat --since 2024-01-01 --out top.json --min-priority 80
# Schritt 2: Kontext für die ersten fünf (online ca. 60 s) oder nur aus mitgelieferten Belegen (--light, kein Netz)
python -m context shortlist.json dossiers.json --limit 5
python -m context shortlist.json dossiers.json --limit 5 --light
# Schritt 3: Scores aus dem ContextResult (Details im README)
python -m scoring dossiers.json --out scoring_out
~~~

**Was der Score enthält:** Schritt 2 baut aus dem Katalogsignal offline einen `Grant` (`catalogue_grant`, auch
`--light`). Bewertet werden nur förderbasierte Kriterien („Vollzeit-Signal: EXIST-…“, „Bisherige Förderung“),
der Rest bleibt neutral: 03EF 53,7, 03EG 52,8, Confidence 0,14. Online blieb es für die Top 5 bei 53,7 (keine
Website, keine idw-Treffer). Die Priorität aus Schritt 1 fließt nicht in den Score ein.

Begriff: `shortlist.json` ist die Fundliste aller Prüffälle, nicht die „Shortlist“ der Sourcing-Regeln (bis zu fünf
priorisierte Kandidaten); die treffen erst `--min-priority` und `python -m context --limit`.

**CLI**: `--out` (Pflicht), `--since` (Standard `FOEKAT_SINCE` oder 2024-01-01), `--programme ef|eg|both`,
`--industry` (`Industry`-Wert oder `ai`, `software`, `health`, `climate`, `fintech`, `industrial`, `deeptech`),
`--min-priority 0–100`, `--include-unclassified` (Standard) / `--no-unclassified`, `--limit n` (nach
Sortierung), `--as-of JJJJ-MM-TT` (Stichtag der Priorität), `--cache PFAD|off`, `--stats`, `--raw-dir`
(Roh-Exporte aus dem Cache). `--stats`: `complete`, `warnings`, `queries`, `requests`, `budget`, `prefixes`, `as_of`, Zählungen je Programm,
Branche, Grundlage, HTGF-Sektor, Flag, `priority_histogram`, `top10`, Filter, `selected` (gefiltert, vor `--limit`). **Exit-Codes:** `0` vollständig, `1` Export unvollständig
(Datei wird trotzdem geschrieben, Warnung auf stderr), `2` Abbruch durch `ExportError` (keine Datei).

**Python:** `search(criteria, *, include_unclassified=False, as_of=None)` liefert die Leads
von `criteria.industry`: erst Grundlage `thema`, dann `institut`, jeweils nach Priorität, Projektbeginn, `id`;
`criteria.limit` gilt nach dem Sortieren. **Unterschied:** `search` lässt Leads mit Programmstandard
(Grundlage `default`) weg, außer mit `include_unclassified=True` (dann zuletzt); die CLI gibt sie aus, außer
mit `--no-unclassified`. `ExportError` und „unvollständig ohne validierte Zeile“ werden zu `SourcingError`;
bei unvollständigem Export mit validierten Zeilen liefert `search` die validierte Teilmenge, protokolliert eine
Warnung (Logger `sourcing.engine`) und setzt an der zurückgegebenen Liste (`SourcingLeads`, ein `list`)
`complete=False` und `warnings`.

## Ablauf des Abrufs

`GET StartAction.do` (Cookie `JSESSIONID`) → `POST SucheAction.do` (`actionMode=searchlist`,
`suche.detailSuche=true`, `suche.fkzSuche[0]=03EF%`, `suche.laufzeitVonSuche[0]=01.01.2024`, `suche.lfdVhb=N`
inkl. Abgeschlossener, `suche.nurVerbund=N`, `suche.ZeSt=ZE`; Seite nennt „<n> Treffer insgesamt“ oder „Keine
Treffer“) → `GET SucheAction.do?actionMode=print&presentationType=csv` (ganze Trefferliste). `laufzeitBisSuche`
filtert auf Projekt**ende** ≤ Datum, darum teilen wir nicht wie der Scraper der Technologiestiftung nach Jahr.

**Prüfung:** Die Zahl eindeutiger FKZ im Export muss der Trefferzahl entsprechen.
- **Weniger FKZ** oder Antwort über der Größengrenze (erkannt an Meldung, HTTP 413, Attribut `too_large` oder
  Ausnahmetyp): Aufteilung nach dem nächsten FKZ-Zeichen (`03EF0…9`, `03EFA…Z`), höchstens 2 Ebenen, Dedupe
  über die FKZ. Bleibt eine Lücke: `complete=False` mit Warnung.
- **Mehr FKZ** als Treffer: keine Aufteilung; Export ungeprüft übernommen, `complete=False` mit Warnung.
- FKZ, die nicht zum Präfix passen oder vor `--since` beginnen, werden mit Warnung verworfen.

**Abbruch** (`ExportError`, kein stiller Ersatz): `ExportNetworkError` (Netz/HTTP nach Wiederholungen),
`NotCsvError` (HTML statt CSV), `MissingColumnError` (Unterklasse davon; nennt die fehlenden Pflichtspalten
aus FKZ, Thema, Laufzeit von/bis, Fördersumme, Förderempfänger, Ausführende Stelle, Staat beider),
`EmptyExportError` (Treffer, aber Export leer oder nur Kopfzeile), `ResultPageError` (Seite ohne Trefferzahl),
`BudgetExhaustedError`. Bei `NotCsvError` wird die Sitzung einmal neu geöffnet und Suche plus Export
wiederholt; erst der zweite Fehler bricht ab.

**Anfragebudget:** `export_rows(..., budget=DEFAULT_BUDGET)`, `DEFAULT_BUDGET = 60` Netzanfragen je Aufruf
(Cache-Treffer kosten nichts). Ein Volllauf braucht 5 (einmal Start, je Präfix Suche und Export), eine
Wiederholung nach `NotCsvError` 3 mehr. `ExportResult` meldet zusätzlich `fetches`, `requests`,
`budget`, `retrieved_at` (älteste Abrufzeit), `prefixes` (je Präfix Treffer vs. FKZ) und `as_dict()`; `--stats`
übernimmt davon `complete`, `warnings`, `queries`, `requests`, `budget`, `prefixes`.

**Bereinigung:** ISO-8859-15 (0xA4 = €), UTF-8-BOM entfernt; Zeilen enden nur an `\n`/`\r\n`, nie innerhalb
`="…"` (Umbrüche im Thema bleiben in der Zelle); Trennung an `;` außer in `="…"`; Wrapper entfernt,
verdoppelte Anführungszeichen (`""`) zurückgeführt; doppelte Geo-Spalten als `… (Förderempfänger)` /
`… (Ausführende Stelle)`; Beträge als `Decimal`. Vom Katalog durch `?` ersetzte Zeichen bleiben so.

## Ausgabe: ein Lead

Echtes Beispiel aus `examples/sourcing/shortlist.json` (gekürzt, Werte wörtlich):

~~~json
{"id": "foekat-03efby0340", "name": "Aiina-Robotics",
 "description": "„Aiina-Robotics“ – Projekt im Programm EXIST-Forschungstransfer.",
 "industry": "Industrial / DeepTech", "htgf_sector": "industrial_deep_tech", "country": "DE", "location": "Garching b. München",
 "source_name": "Förderkatalog des Bundes", "source_url": "https://foerderportal.bund.de/foekat/jsp/SucheAction.do?actionMode=view&fkz=03EFBY0340",
 "country_evidence": {"field": "country", "finding": "Förderkatalog FKZ 03EFBY0340: Förderempfänger Technische Universität München (TUM), Ort Muenchen, Bundesland Bayern, Staat Deutschland; Ausführende Stelle …", "retrieved_at": "2026-11-20T22:32:24Z"},
 "is_demo": false, "website": null, "founders": [], "contact_email": null, "founding_year": null, "founding_month": null, "has_vc": null,
 "signals": [{"source": "Förderkatalog", "type": "exist_projekt", "date": "2025-05-01", "subject_lead_id": "foekat-03efby0340",
   "evidence": "Förderkennzeichen: 03EFBY0340\nProgramm: EXIST-Forschungstransfer\nThema: Aiina-Robotics\nFörderempfänger: Technische Universität München (TUM), Muenchen, Bayern\nAusführende Stelle: … Lehrstuhl für Robotik, Künstliche Intelligenz und Echtszeitsysteme, Garching b. München, Bayern\nLaufzeit: 01.05.2025 bis 30.04.2027\nFördersumme: 1.223.361,00 EUR\nÖffentliche Förderung: Bewilligt\nHinweise: early_signal_exist, founding_date_unknown, founders_unknown, pre_founding_team, internal_review_case, industry_basis_thema"}],
 "prioritization_reason": "Priorität 90: EXIST-Forschungstransfer; Förderung endet 04/2027; Branche Industrial / DeepTech aus Projekttitel (robot); 1.223.361 EUR."}
~~~

- **id:** `foekat-` + FKZ klein. **name:** Thema ohne Präfix („EXIST-Forschungstransfer:“) und ohne
  Personennamen; „(ehemals X)“ bzw. „Name ehemals X“ wird abgetrennt; lange alte Themen (> 60 Zeichen)
  behalten den Teil vor „ - “. Leeres Thema → Name = FKZ (Warnung im Log). Das ist ein **Projektname**.
- **description:** `„<Name>“[ (ehemals „<X>“)][: <Rest des Themas>] – Projekt im Programm <Programm>.`
- **signals:** eines je FKZ, `date` = Projektbeginn, `subject_lead_id` = Lead-ID. `evidence` hat je Zeile ein
  Label: `Förderkennzeichen`, `Programm`, `Thema`, `Förderempfänger` und `Ausführende Stelle` (Name, Ort,
  Bundesland), `Laufzeit` (`TT.MM.JJJJ bis TT.MM.JJJJ`), `Fördersumme` (`… EUR`), `Öffentliche Förderung:
  Bewilligt` (liest `scoring_input` als bewilligte Förderung), `Hinweise:` (Flags). Schritt 2 liest das
  offline (`context.engine.parse_catalogue`/`catalogue_grant`). `exist_projekt` steht in `NO_QUOTE_TYPES`
  (`context/classify.py`): Katalogtext wird nie als Firmenaussage zitiert.
- **country="DE"** nur, wenn die Zeile „Deutschland“ als Staat von Empfänger oder Ausführender Stelle nennt,
  sonst übersprungen (`skipped_non_de`). **location:** Ort der Ausführenden Stelle, sonst des Empfängers.
  **Leer** bleiben `founders`, `contact_email`, `website`, `founding_year/-month`, `has_vc`.
- **Reihenfolge der CLI-Liste:** Priorität absteigend, Projektbeginn absteigend, `id`.
- **Verbund:** gleiches nicht leeres „Projekt“ (`foekat-verbund-<projekt>`) oder FKZ bis auf einen
  Endbuchstaben gleich (`…0063A`/`…0063B`) ergibt einen Lead mit einem Signal je FKZ. Ab 2024 kommt beides
  nicht vor (733 Zeilen = 733 Leads); nur an konstruierten Fällen getestet.

**Flags** (Zeile `Hinweise:` im Signal und `SourcingRun.info[id].flags`, nicht mehr im Grund; 20.11.2026):

| Flag | Bedeutung | Anzahl |
| --- | --- | --- |
| `early_signal_exist`, `founding_date_unknown`, `founders_unknown` | immer | 733 |
| `pre_founding_team`, `internal_review_case` | Empfänger ist keine Firma | 733 |
| `recipient_company` (+ `exist_ft_phase2_candidate`) | 03EF-Empfänger mit Rechtsform (nicht gGmbH), nichts klingt akademisch | 0 |
| `industry_basis_thema` / `_institut` / `_default` | Grundlage der Branche | 83 / 302 / 348 |
| `industry_unclassified` | keine Branchenregel traf | 348 |
| `project_finished` | Projektende vor dem Stichtag | 388 |
| `verbund` | mehrere FKZ in einem Lead | 0 |
| `executing_country_unassigned` | Staat der Ausführenden Stelle nicht „Deutschland“ | 1 |

## Branche, HTGF-Sektor, Priorität

**Grundlage:** `thema` (Regel trifft das Thema; verlässlich), `institut` (erst Ausführende Stelle, dann
Förderempfänger, jeweils ohne Personennamen; schwach), `default` (kein Treffer: 03EF → Industrial / DeepTech,
03EG → AI / Software, `htgf_sector=null`, Flag `industry_unclassified`, Grund „Branche nicht klassifiziert
(Programmstandard …)“).

Schlüsselwörter treffen nur ganze Token (Kleinschreibung, Trennung an Nicht-Buchstaben und CamelCase:
„SherpAI“ → sherp, ai): `stem` = Token beginnt so, `*stem` = auch im Kompositum („Hautkrebs“), `<tok>` = genau
dieses Token, `a b` = aufeinanderfolgende Token; `<carbon>` zählt nur mit einem weiteren Klima-Treffer. Im
ersten Feld mit Treffer gewinnt die Regel mit den meisten Treffern, bei Gleichstand die frühere Tabellenzeile.

| Regel (Gleichstand-Reihenfolge) | `industry` | `htgf_sector` | Beispiele |
| --- | --- | --- | --- |
| fintech | FinTech | digital_tech | finanz, `<bank>`, `*versicher`, payment, `<pay>`, blockchain |
| health | HealthTech | life_sciences | `*medizin`, `*klinik`, pharma, `*therap`, `*diagnos`, `*krebs` |
| climate | ClimateTech | climate_tech | `*energie`, `*klima`, solar, `*wasserstoff`, batter, recyc, agrar |
| chemistry_materials | Industrial / DeepTech | chemie_materialien | chemie, `*werkstoff`, material, polymer, `*katalys` |
| industrial_deeptech | Industrial / DeepTech | industrial_deep_tech | maschinen, produktion, robot, `*laser`, quanten, `*sensor`, `<space>` |
| software_ai | AI / Software | digital_tech | informatik, software, `<ki>`, `<ai>`, daten, digital, cyber |

Verteilung (thema / institut / default): AI / Software 446 (42 / 83 / 321), Industrial / DeepTech 182
(17 / 138 / 27), HealthTech 67 (12 / 55 / 0), ClimateTech 34 (9 / 25 / 0), FinTech 4 (3 / 1 / 0).
HTGF-Sektoren: digital_tech 129, industrial_deep_tech 123, life_sciences 67, climate_tech 34,
chemie_materialien 32 (nur über `htgf_sector` filterbar, nicht über `--industry`).

**Priorität** (0–100, `PRIORITY_WEIGHTS` in `mapping.py`) zum Stichtag `as_of` (Standard: späteste Abrufzeit
der Exportzeilen, nie `date.today()`, daher reproduzierbar): 03EF +40; Förderende zwischen Stichtag − 12 und
+ 6 Monaten +25, später +10, früher 0; Grundlage `thema` +15, `institut` +5; Bundesanteil ≥ 500.000 € +10,
≥ 100.000 € +5; Empfänger ist Firma +10. Grund: `Priorität N: <Programm>; <Laufzeit>; <Branche und
Grundlage>; <Summe> EUR[; Empfänger ist ein Unternehmen].` Verteilung: 90–100: 6, 80–89: 48, 70–79: 11,
60–69: 75, 50–59: 6, 40–49: 45, 30–39: 291, 0–29: 251.

Top 10 (alle 03EF; Priorität, Branche/Grundlage, Förderende, Summe): **90** Aiina-Robotics (Industrial,
thema, 04/2027, 1.223.361 €), DataLingua (AI, thema, 03/2027, 1.003.023 €), Pulse-of-Production (Industrial,
thema, 12/2026, 811.703 €), sensAI (AI, thema, 07/2026, 598.747 €), VersatileRobotics (Industrial, thema,
03/2026, 1.064.409 €), SpaceMast (Industrial, thema, 03/2026, 1.275.102 €); **80** M-Shunt, SUNEO, KM,
SoreAlert (alle Industrial, institut, 03–04/2027, 0,98–1,42 Mio. €).

## Grenzen

- **Verzug:** Vorhaben erscheinen „frühestens 60 Tage nach der Bewilligung“ und nur, was Ressorts freigeben.
- **Alles sind Projekte vor der Gründung.** Empfänger ist in allen 733 Zeilen eine Hochschule oder ein
  Institut; der DE-Beleg belegt deren Sitz, nicht den einer Firma.
- **Projektname ≠ Firmenname.** Erst Schritt 2 (Impressum, Register) kann eine Firma belegen (`match_confidence`).
- **Gründungsstipendium ≠ VC-Fall.** Viele 03EG-Teams gründen nicht oder bauen kein skalierbares Geschäft.
- **Keine Gründer:innen im Katalog**, daher ist das OpenAlex-Kontingent irrelevant (keine Abfrage ohne Gründer).
- **Branche:** 348 von 733 (47 %) nur Programmstandard, 302 nur aus dem Institut. `search` liefert ohne
  Option höchstens die 385 klassifizierten Leads, `pipeline.discover` zusätzlich höchstens
  `SearchCriteria.limit` (Standard 30, max. 200).
- **Score:** Light-Scores unterscheiden sich in unseren Stichproben nur nach Programm (53,7 / 52,8); die
  Priorität ist kein Teil davon.

## Last, Cache, Determinismus

`context.foekat.Session`: User-Agent `FounderRadar/1.0 (research prototype)` (ohne Kontakt), 1 Anfrage/s,
Timeout 20 s, 2 Wiederholungen bei 429/5xx/Netzfehlern, max. 3 MB; öffnet erst bei Cache-Fehlschlag. Cache:
ein Eintrag je Suche+Export in `.cache/context.db` (TTL 14 Tage, `--cache off`/`CONTEXT_CACHE=off`), Schlüssel
`foekat-export:v1:` + sha1 des Formulars, Fehler nie gecacht. Mit Cache sind Läufe byte-identisch (geprüft) und
ohne Netz; innerhalb der 14 Tage sieht ein Lauf keine neuen Vorhaben.

**Andere Programme:** `export_rows(prefixes=(…, "<neu>"))` genügt für den Abruf; anzupassen sind `PROGRAMMES`, `DEFAULT_INDUSTRY`,
`project_key`, `_PREFIX`, `SIGNAL_TYPE`, Flags, `PRIORITY_WEIGHTS`/`recipient_is_company` (03EF-spezifisch),
`PROGRAMME_PREFIXES`. Schritt 2 liest jede FKZ aus `Förderkennzeichen:`. Vorher prüfen: Export unter 3 MB.

## Lizenz, Nutzungsbedingungen, Datenschutz

**Scraper.** Vorgehen (nicht Code) aus [technologiestiftung/udb-foerderkatalog-scraper](https://github.com/technologiestiftung/udb-foerderkatalog-scraper)
(MIT, © 2026 Technologiestiftung Berlin); Abgleich mit Commit `bbf54e1` fand nur Server-Formularfelder und die
Treffer-Regex als Gemeinsamkeit. Keine Lizenzkopie nötig; Namensnennung in `NOTICE.md`.

**Förderkatalog.** Herausgeber BMFTR, Betrieb DLR-IP. Impressum und Datenschutzerklärung (20.11.2026) enthalten **keine
Nutzungsbedingungen und keine Lizenz**, zu automatisiertem Abruf nichts; `robots.txt` antwortete 403. Quelle
steht an jedem Lead; vor Weitergabe außerhalb des Hackathons bei foekat@dlr.de nachfragen.

**DSGVO.** Ausführende Stellen nennen teils Professor:innen. Schritt 1 entfernt Namen mit akademischem Titel
(`strip_persons`, Regeln in `context/text.py`: „…, Prof. Dr. Erika Musterfrau“) und untitelte Arbeitsgruppenleitungen der Form
„AG Vorname [van/von] Nachname“ am Ende eines Abschnitts aus Name, Beschreibung, Signal, `country_evidence` und
vor der Branchenzuordnung; Fach-AGs („AG Künstliche Intelligenz“, „AG Autonome Intelligente Systeme“) und nach
Personen benannte Lehrstühle („Dr. Theo Schöller-Stiftungslehrstuhl“) bleiben.
Besteht ein Feld nur aus einer Person, wird es leer („?“ im Signal). Schritt 2 (`context/foekat.py`,
`context/engine.py`) wendet dieselbe Funktion auf Thema, Empfänger und Ausführende Stelle an.
**Bekannte Lücken:** Namen ohne Titel außerhalb der AG-Form („Leitung: Vorname Nachname“, „Arbeitsgruppe
Nachname“, „Lehrstuhl X (Nachname)“, „Lehrstuhl Y - Vorname Nachname“), Namen in Großbuchstaben, „AG Vorname
Nachname“ ohne Hochschul-/Institutsbezeichnung im selben Feld (die AG-Regel ist eine Heuristik über
Wortendungen); Cache und `--raw-dir` enthalten die unveränderten Zeilen.
Gründer:innen, E-Mails oder Telefonnummern werden nicht abgeleitet. Rechtsgrundlage und Löschfrist sind offen.
