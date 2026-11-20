# Scoring – Übergabe an das Matrix-Team

Das Scoring nimmt pro Unternehmen ein Lead-Dossier und liefert eine Zeile mit drei Achsen, Gesamtscore, Stage, Texten und Belegen. Die Matrix bzw. Visualisierung baut der nächste Schritt.

## Aufruf

```bash
python -m scoring <leads.json | ordner | leads.db> --out scoring_out --stichtag 2026-11-20
```

Ergebnis im Zielordner: `scores.csv`, `scores.json` (gleiche Daten, Liste von Objekten) und `scores.schema.json`. Jede Zeile wird vor dem Schreiben gegen das Schema geprüft. Verletzt eine Zeile das Schema, steht sie als `zurueck_an_sourcing` mit Grund im Export, der Lauf endet mit Exit-Code 1 und alle anderen Zeilen bleiben erhalten. Doppelte `lead_id` bekommen das Suffix `-dup2`, `-dup3` … Textzellen der CSV, die mit `=`, `+`, `-` oder `@` beginnen, bekommen ein vorangestelltes `'`, damit Excel sie nicht als Formel ausführt; `scores.json` enthält den Originalwert. Ein Beispiel aus erfundenen Dummy-Leads liegt in `examples/scoring/`.

`--stichtag` legt das Bezugsdatum für Alter und Earliness fest. Mit demselben Stichtag liefert derselbe Input immer dieselben Werte. Ohne Angabe gilt das heutige Datum. Signale zählen nur mit taggenauem Datum (`JJJJ-MM-TT` oder `TT.MM.JJJJ`) bis zum Stichtag; aus einem Jahr allein wird kein Tag gemacht. Dasselbe gilt für `first_db_date` und für das `datum` in `evidence`.

Im Dashboard läuft dieselbe Logik über `evaluation.engine.evaluate(EnrichedLead)`.

## Die drei Achsen

| Spalte | Richtung | Kriterien (Gewicht in der Achse) |
|---|---|---|
| `team_score` | 100 = stark | Forscher-Match über Papers im Produktfeld (35 %), komplementäres Gründerteam (25 %), Vollzeit-Signal wie EXIST (20 %), Vorerfahrung (20 %) |
| `marktpotenzial_score` | 100 = groß | belegtes Marktvolumen (30 %), Partner/Piloten/Kunden (30 %), Skalierbarkeit nach Produkttyp (20 %), Zielkunde und Modell benannt (10 %), Wettbewerber (10 %) |
| `risiko_score` | **100 = hohes Risiko** | Reifegrad der Technologie (40 %), Regulatorik (20 %), Schutzrechte (15 %), bisherige Förderung (15 %), Datenlage (10 %) |

`team_score` ist die dritte Achse. Ihr Anzeigename steht in jeder Zeile in der Spalte `dim3_name` (aktuell "Team") und lässt sich in `scoring_config.yaml` ändern; der Spaltenname `team_score` bleibt gleich.

## Formel

```
gesamt_score = 0,35 · team_score + 0,35 · marktpotenzial_score + 0,30 · (100 − risiko_score)
```

Alle Gewichte und Punktetabellen stehen in `scoring/scoring_config.yaml`. Die Datei prüft beim Laden, dass die Gewichte jeweils 1,0 ergeben.

## Regeln

- **Beleg-Pflicht.** Ein Fakt zählt nur, wenn er im Dossier selbst eine Quellen-URL trägt: `{"wert": …, "quelle": "https://…"}` bzw. `quelle` am Listeneintrag (bei Teammitgliedern auch `openalex`). Es gibt keine Ersatzquellen. Das gilt auch für den Beschreibungstext, Rechtsform, Gründungsdatum, Finanzierungsmeldung und die Noise-Regeln. Ohne Beleg geht ein Kriterium mit 50 Punkten ein, steht in `evidence` als "keine Daten – neutral gesetzt" und in `offene_punkte`.
- **Ausnahme: vier Sourcing-Metadaten ohne URL.** `noise_class`, `match_confidence`, `in_databases` und `first_db_date` werden übernommen, weil sie das Ergebnis des Sourcing-Schritts selbst sind. In den Texten steht dann "laut Sourcing".
- **Branche** ist nur ein Label und bewegt keinen Score.
- **Confidence (0–1).** Anteil der belegten Kriterien nach Gewicht, multipliziert mit `match_confidence` aus dem Sourcing. Liegt `match_confidence` unter 0,5, steigt zusätzlich das Kriterium Datenlage im Risiko auf 90 Punkte. Ein Lead ganz ohne Zusatzdaten landet bei etwa 50 Punkten mit Confidence unter 0,1. Bitte in der Matrix nach `confidence` filtern oder einfärben, sonst sehen datenarme Leads wie Mittelfeld aus.
- **Harte Ausschlüsse.** `noise_class` ungleich `vc_potenzial` oder `stage = zu_spaet` deckelt `gesamt_score` auf 20. Der Grund steht in `ausschluss_grund`. Die drei Achsenwerte bleiben unverändert.
- **Pflichtangaben.** Fehlen Name, Beschreibungstext, ein datiertes Signal mit URL oder der Deutschland-Beleg, wird nicht bewertet: `status = zurueck_an_sourcing`, alle Scores sind leer, `confidence = 0,1`.
- **E-Mail.** Nur generische Postfächer (`info@`, `kontakt@` …) mit Quelle und auf der Domain der eigenen Website. Alles andere wird verworfen und die Spalte bleibt leer.

## Stage

| Wert | Regel |
|---|---|
| `zu_spaet` | belegte Finanzierungsmeldung, `noise_class = bereits_finanziert` oder belegtes Gründungsdatum älter als 36 Monate. Ist nur das Gründungsjahr bekannt, zählt der 31.12. Ein Datenbank-Eintrag allein reicht nicht (Schalter `zu_spaet_wenn_in_databases`) |
| `pre_gruendung` | keine Kapitalgesellschaft belegt. Das gilt auch, wenn die Angabe fehlt, nicht mit GmbH, gGmbH, UG, AG oder SE endet (z. B. GbR, e.V., "AG Müller") oder eine Verneinung bzw. einen Plan enthält ("noch keine GmbH", "GmbH geplant") |
| `in_gruendung` | GmbH, gGmbH, UG, AG oder SE mit "i.G.", "i.Gr." oder "in Gründung" |
| `seed` | GmbH, gGmbH, UG, AG oder SE und belegter Reifegrad `pilot` oder `erste_kunden` |
| `pre_seed` | GmbH, gGmbH, UG, AG oder SE sonst; oder belegtes Gründungsdatum ohne belegte Rechtsform |

## Noise-Klasse

Liefert das Sourcing eine `noise_class`, gilt sie. Sonst greifen diese Regeln, jeweils nur mit Quelle am Feld:

| Wert | Regel |
|---|---|
| `bereits_finanziert` | belegte Finanzierungsmeldung |
| `agentur` / `beratung` | mindestens zwei verschiedene Agentur-Wörter als ganze Wörter im `website_text` (Liste in der Konfiguration); `beratung`, wenn mindestens die Hälfte davon Beratungs-Wörter sind |
| `studi_projekt` | `repo_art` ist `kurs` oder `seminar` |
| `hobby` | `repo_art` ist `hobby`, oder: genau eine belegte Person, Rechtsform ausdrücklich `keine`, und weder Förderung noch Patent, Partner oder Papers belegt |
| `vc_potenzial` | sonst |

## Weitere Spalten

- `gruendungsjahr`, `gruendungsmonat`: belegtes Gründungsdatum, sonst der Start einer belegten EXIST-Förderung. Dann ist `gruendung_ist_proxy = true`. Ist nur das Jahr bekannt, bleibt der Monat leer.
- Als EXIST zählt nur ein Eintrag, dessen `programm` ein EXIST-Programmname ist (z. B. "EXIST-Forschungstransfer"), der ein Startdatum hat, nicht in der Zukunft beginnt und nicht länger als 12 Monate beendet ist. Fehlt das Enddatum, gilt eine Laufzeit von 36 Monaten. Nur exakt gleiche Einträge werden zusammengefasst; der SQLite-Lader fasst zusätzlich Signale mit demselben Förderkennzeichen zusammen.
- `name_gruender`: nur Personen mit Quelle.
- `evidence`: Liste aus `{dimension, kriterium, aussage, url, datum, punkte}`. `dimension` ist `team`, `marktpotenzial`, `risiko`, `stage` oder `noise`. In der CSV als JSON-Text in einer Zelle.
- `teilwerte`: Punkte, Gewicht und Beleg-Status je Kriterium.
- `earliness_delta_monate`: Monate vom ersten Signal bis zum ersten Datenbank-Eintrag, ohne Eintrag bis zum Stichtag. Liegt der Datenbank-Eintrag vor dem ersten Signal, ist der Wert 0. Ein Eintragsdatum nach dem Stichtag wird ignoriert.
- `produktbeschreibung` (erste zwei Sätze) und `value_proposition` (erster Satz): wörtlich aus dem Beschreibungstext, nur gekürzt. `investmenthypothese` und `why_now`: aus belegten Kriterien und den vier Sourcing-Metadaten zusammengesetzt. Bei einem Ausschluss lautet die Hypothese "Kein Investment-Case: …", bei Confidence unter 0,3 "Datenlage zu dünn für eine Hypothese …". Es formuliert kein Sprachmodell.
- Leere Zellen in der CSV bedeuten "unbekannt", nicht null.

## Herkunft des Verfahrens

Faktoren und Ausgangsgewichte stammen aus Scorecard (Bill Payne), Berkus und Risk Factor Summation, wie sie [startup-valuation](https://github.com/simonmak-ascent/startup-valuation) (MIT) implementiert. Geändert wurde:

- Feste Regelstufen über belegte Fakten statt frei geschätzter Multiplikatoren.
- Fehlende Daten sind neutral statt schlechtester Wert.
- Teamlücken stehen nur in `team_score`, der Produkttyp nur in `marktpotenzial_score`, damit die Achsen nicht dasselbe messen. Mehrfach genutzt werden: eine EXIST-Förderung (Vollzeit-Signal im Team, Summe im Risiko, Start als Ersatz-Gründungsdatum), der Reifegrad (Risiko und die Grenze zwischen `pre_seed` und `seed`), `match_confidence` (Confidence und Datenlage), die Rechtsform (Stage und Hobby-Regel), die Finanzierungsmeldung (Noise-Klasse und Stage) sowie Förderung, Patent, Partner und Papers (Score und Hobby-Regel).
- Alles, was Umsatz, Vergleichsbewertungen oder Cap Table braucht (VC-Methode, DCF, Multiples), entfällt.

## Mapping auf das Dashboard-Modell (`models.EvaluatedLead`)

| Scoring | Dashboard |
|---|---|
| `gesamt_score` | `overall_score` |
| `team_score` | `company_score` |
| `marktpotenzial_score` | `market_potential_score` |
| `risiko_score` | `risk_score` |
| `confidence` × 100 | `confidence_score` |
| `pre_gruendung`, `in_gruendung`, `pre_seed` | `Pre-Seed` |
| `seed` | `Seed` |
| `zu_spaet` | `Early Growth` |
| nicht bewertet | `Unbekannt` |
| belegte Aussagen | `score_drivers`, `risks` |
| `offene_punkte` | `open_questions` |

## Offen

- Die Gewichte sind nicht kalibriert. Dafür fehlen noch 10 von Hand bewertete Leads.
- Seit dem 20.11.2026 liefert der Kontext-Schritt Rechtsform, Förderung, Papers je Gründer, IP, Partner und Produkttyp mit Quellen (`context/ENRICHMENT.md`); `evaluation/engine.py` reicht sie durch. Die **Demo-Leads** des Dashboards haben diese Felder nicht und landen weiter bei drei Gesamtscores (50,0 / 52,4 / 54,2); echte Leads siehe `examples/context/scores/`.
- Die Textklassifikation (Reifegrad, Produkttyp, Regulatorik, Partner) ist die schwächste Quelle: im ersten Faktencheck waren rund zwei Drittel ihrer Werte falsch oder schwach belegt, vor allem durch Pressemeldungen über andere Firmen. Harte Quellen (Impressum, Förderkatalog, Wayback, OpenAlex) stimmten in über 90 % der Fälle.
- Der Dashboard-Weg übersetzt `product_stage` und `funding_stage` nur bei exakter Übereinstimmung mit einer festen Liste (siehe `evaluation/engine.py`) und nur mit passendem Evidence-Eintrag.
- Ein Sprachmodell für weiche Kriterien ist nicht eingebaut.
- Der SQLite-Lader übernimmt eine Fördersumme nur, wenn im Signaltext genau ein Betrag in deutscher Schreibweise steht ("650.000 EUR"). Sonst bleibt die Summe leer. Als Deutschland-Beleg nimmt er den Textausschnitt eines Förderkatalog- oder Impressum-Signals, ohne den Inhalt zu prüfen.
- Die Agentur-Regel erkennt keine Verneinung ("Wir sind keine Agentur und bieten keine Beratung" gilt als Beratung).
- `lead_id` wird bereinigt (Steuerzeichen zu Leerzeichen, höchstens 120 Zeichen). Ein Dossier ohne `lead_id` und ohne lateinischen Namen bekommt eine Hash-ID.
- Bei einem Ordner als Input wird eine unlesbare Datei mit Warnung übersprungen.
- Ob eine Quelle die Aussage wirklich stützt, prüft das Scoring nicht. Es prüft nur, dass das Sourcing zu jedem Fakt eine Quelle mitliefert.
- Datenarme Leads liegen bei rund 50 Punkten und damit über ausgeschlossenen Leads (maximal 20).
