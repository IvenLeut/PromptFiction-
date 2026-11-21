# Scoring – Übergabe an das Matrix-Team

Das Scoring nimmt pro Unternehmen ein Lead-Dossier und liefert eine Zeile mit drei Achsen, Gesamtscore, Stage, Texten und Belegen. Die Matrix bzw. Visualisierung baut der nächste Schritt.

## Aufruf

```bash
python -m scoring <dossiers.json | context_result.json | ordner | leads.db> --out scoring_out --stichtag 2026-11-20
```

Input: eine Liste von Scoring-Dossiers (Format unten, z. B. `scoring/testleads/dummy_leads.json`), ein `ContextResult` bzw. eine Liste von Leads aus Schritt 1/2 (erkannt an `source_url` + `industry`, z. B. `examples/sourcing/sample_dossiers.json`), ein Ordner mit solchen Dateien oder eine SQLite-DB im Plan-v4-Format (`scoring/sources.py`). Leads werden wie im Dashboard mit `evaluation.engine.to_dossier` übersetzt; ein mitgelieferter `scoring_input` wird darübergelegt. Damit führt `python -m scoring` direkt von der Sourcing-Ausgabe zu Scores. Unterschiede zur Pipeline: die CLI nimmt den gespeicherten `scoring_input` (`pipeline.evaluate_context` baut ihn neu) und als Stichtag immer `--stichtag` bzw. heute, nie `scoring_input.as_of`. Eine Datei gilt nur als Lead-Liste, wenn jeder Eintrag `source_url` und `industry` und kein `name_unternehmen` hat; ein ungültiger Lead wird mit Warnung zu einer Zeile `zurueck_an_sourcing`.
Die Eingabe kann auch eine Liste eingefrorener `ScoringInput`-Objekte sein (erkannt an `rules_version` + `lead_id`). Ein eingefrorener Export verwendet seinen gespeicherten Stichtag (`as_of`); ein abweichender `--stichtag` bricht mit Fehler ab. Für einen anderen Stichtag den Kontext-Export verwenden. Bei Leads gilt `--stichtag` auch als Belegstichtag: Evidence, Signale, Förderungen, Partner und Profile mit späterem Datum oder aus einer Quelle, die laut Kopfzeile zu einer anderen Firma gehört (`scoring_input.source_binding`), zählen nicht. Der Import älterer SQLite-Dateien erwartet eine Tabelle mit Leads und expliziten Deutschland-Belegen zu den jeweiligen Leads.

Ergebnis im Zielordner: `scores.csv`, `scores.json` (gleiche Daten, Liste von Objekten) und `scores.schema.json`. Jede Zeile wird vor dem Schreiben gegen das Schema geprüft. Verletzt eine Zeile das Schema, steht sie als `zurueck_an_sourcing` mit Grund im Export, der Lauf endet mit Exit-Code 1 und alle anderen Zeilen bleiben erhalten. Doppelte `lead_id` bekommen das Suffix `-dup2`, `-dup3` … Textzellen der CSV, die mit `=`, `+`, `-` oder `@` beginnen, bekommen ein vorangestelltes `'`, damit Excel sie nicht als Formel ausführt; `scores.json` enthält den Originalwert. Ein Beispiel aus erfundenen Dummy-Leads liegt in `examples/scoring/`.

`--stichtag` legt das Bezugsdatum für Alter und Earliness fest. Mit demselben Stichtag liefert derselbe Input immer dieselben Werte. Ohne Angabe gilt das heutige Datum. Signale zählen nur mit taggenauem Datum (`JJJJ-MM-TT` oder `TT.MM.JJJJ`) bis zum Stichtag; aus einem Jahr allein wird kein Tag gemacht. Dasselbe gilt für `first_db_date` und für das `datum` in `evidence`.

Im Dashboard läuft dieselbe Logik über `evaluation.engine.evaluate(ScoringInput, lead=EnrichedLead)` (auch `evaluate(ScoringInput)` und `evaluate(EnrichedLead)`). Der Stichtag ist dort `as_of=`, sonst `ScoringInput.as_of`, sonst heute.

## Dossier-Felder

Ein Dossier ist ein JSON-Objekt. Gelesen werden: `lead_id`, `name_unternehmen`, `beschreibung_rohtext`, `deutschland_beleg`, `website`, `email`, `branche` (oder `htgf_bereich`), `rechtsform`, `gruendungsdatum`, `gruendungsjahr_hinweis`, `team`, `mix_tech_business`, `vollzeit_signal`, `reifegrad`, `produkt_typ`, `regulierter_markt`, `ip`, `markt` (`zielkunde`, `modell`, `volumen_eur`), `partner`, `wettbewerber`, `foerderung` (je Eintrag `programm`, `summe_eur`, `start`, `ende`, `quelle`, optional `kennzeichen`, `empfaenger`, `ausfuehrende_stelle`, `thema`), `funding_meldung`, `website_text`, `repo_art`, `noise_class`, `in_databases`, `in_databases_quelle`, `first_db_date`, `match_confidence`, `signals`, `source_url`. Unbekannte Schlüssel werden ignoriert. Welche Lead-Felder der Dashboard-Weg wohin übersetzt, steht als Tabelle im Docstring von `evaluation.engine.to_dossier`.


## Die drei Achsen

| Spalte | Richtung | Kriterien (Gewicht in der Achse) |
|---|---|---|
| `team_score` | 100 = stark | Forscher-Match über Papers im Produktfeld (30 %), komplementäres Gründerteam (20 %), Vollzeit-Signal wie EXIST (15 %), Vorerfahrung (15 %), Forschungsumfeld/Institut (20 %, Proxy) |
| `marktpotenzial_score` | 100 = groß | belegtes Marktvolumen (25 %), Partner/Piloten/Kunden (35 %), Skalierbarkeit nach Produkttyp (10 %), Zielkunde und Modell benannt (5 %), Wettbewerber (5 %), Timing der Förderphase (5 %), Tech-Tiefe aus Programm und Fachgebiet (15 %, Proxy) |
| `risiko_score` | **100 = hohes Risiko** | Reifegrad der Technologie (25 %), Regulatorik (15 %), Schutzrechte (15 %), bisherige Förderung (20 %), Datenlage (25 %) |

`team_score` ist die dritte Achse. Ihr Anzeigename steht in jeder Zeile in der Spalte `dim3_name` (aktuell "Team") und lässt sich in `scoring_config.yaml` ändern; der Spaltenname `team_score` bleibt gleich.

## Förderkatalog-Auswertung (seit Version 1.1)

Die 733 EXIST-Leads haben meist nur die Katalogseite. Deren Felder (Programm, Förderkennzeichen, Summe, Laufzeit, Förderempfänger, ausführende Stelle, Thema) gehen jetzt mit der Katalog-URL als Beleg ein. `evaluation.engine.to_dossier` liest Stelle und Thema aus dem Signal- bzw. Evidence-Text derselben URL. Ohne diese Felder bleibt alles wie bisher neutral.

| Kriterium | Regel | Art |
|---|---|---|
| `forschungsumfeld` | erste passende, zum Stichtag gültige Klasse aus Empfänger/Stelle: außeruniversitär (Fraunhofer, MPG, Helmholtz, Leibniz, DLR) 0,9 · TU9 oder Exzellenzuniversität 0,85 · andere Universität 0,7 · Hochschule 0,55. Die Exzellenzliste folgt der Förderphase: bis 31.12.2026 die Phase 2019–2026 (mit Konstanz), ab 01.01.2027 die neue Phase (ohne Konstanz, dazu Freiburg, Jena, Köln, Bochum/Dortmund, Frankfurt/Mainz). Quellen in `scoring_config.yaml` | Proxy |
| `komplementaer` (ohne Namen) | Gründungsstipendium: Mindestzahl geförderter Personen = ⌈(Summe − 35.000) / (3.450 · Laufzeitmonate)⌉ nach den Obergrenzen der Richtlinie; ≥ 3 → 0,7, ≥ 2 → 0,6. Forschungstransfer ohne Namen: „Forschungsteam“ 0,6 | Rechnung bzw. Proxy |
| `timing` (5 %) | Belegte GmbH/UG/AG/SE (auch i.G.) und Förderende höchstens 12 Monate entfernt (davor oder danach) → 0,9 („Anschlussfinanzierung steht an“). Sonst Monate bis Förderende: ≤ ±6 = Gründungsfenster 1,0 · in 7–12 0,85 · in 13–24 0,65 · später 0,55 · vor 7–12 0,6 · vor 13–24 0,3 · länger 0,15. Das Gewicht sank von 15 % auf 5 %, weil „Förderung endet bald“ ein Anlass ist, kein Qualitätsmerkmal, und gegründete Teams nach Förderende nicht abgewertet werden dürfen | belegt |
| `tech_tiefe` | Forschungstransfer + technisches Fachgebiet 1,0 · Forschungstransfer 0,85 · technisches Fachgebiet 0,75 · Fachgebiet ohne Technikbezug (Kunst, Design, Sport, Pädagogik, Medien …) 0,3. Wirtschafts-/Entrepreneurship-Lehrstühle zählen bewusst nicht als „ohne Technik“, weil sie oft nur Mentor sind | Proxy |
| `skalierbarkeit` (ohne `produkt_typ`) | Fachgebiet: Informatik/Software/Daten → Software, Ingenieur-/Naturwissenschaft → Hardware, beides → Hardware mit Software, Pharma → Wirkstoff | Proxy |
| `regulatorik` (ohne Angabe) | Medizin-Bezug (Klinik, Charité, Medizin, Pharma …) → reguliert; sonst offen, nie „unreguliert“ | Proxy |
| `finanzierung` | feinere Stufen: ab 1,2 Mio. 0,2 · 0,8 Mio. 0,25 · 0,5 Mio. 0,3 · 130 k 0,4 · 110 k 0,45 · > 0 0,55 | belegt |

Bei einem Proxy wird der Abstand zum Neutralwert mit `katalog.proxy_faktor` (0,75) skaliert. Für die Confidence zählt sein Gewicht nur halb (`confidence_faktor`). In `teilwerte` steht `"proxy": true` und in der Aussage „(Proxy)“. Die Fachgebiets-Regeln lesen nur die Katalogseite und nie Website- oder Pressetexte: Ein Schlagwort in einer Selbstbeschreibung ist eine Behauptung, den Produkttyp daraus liefert der Kontext-Schritt als `produkt_typ`. Alle Muster stehen in `scoring_config.yaml` unter `katalog`.

## Formel

```
gesamt_score = 0,40 · team_score + 0,25 · marktpotenzial_score + 0,35 · (100 − risiko_score)
```

Kalibrierungsrunde 21.11.2026 (vorher 0,35/0,35/0,30). Gründe: Team zuerst („we invest in people“). Die Marktachse besteht bei EXIST-Leads fast nur aus Proxys und Neutralwerten: Marktvolumen, Traktion und Zielkunde sind zu 0–3 % belegt. Das Risiko trägt die belegten Firmenfakten (Datenlage). Sobald Marktdaten kommen, sind die alten Werte wiederherzustellen. Gemessen mit 30 ungeprüften Agent-Labels: Spearman online 0,14 → 0,32, offline 0,01 → 0,22. Die Zahlen sind ein Hinweis, keine Begründung (`AGENT_TEAM/reports/scorer.md`).

Alle Gewichte und Punktetabellen stehen in `scoring/scoring_config.yaml`. Beim Laden wird geprüft, dass alle Schlüssel vorhanden sind und die Gewichte jeweils 1,0 ergeben.

## Regeln

- **Beleg-Pflicht.** Ein Fakt zählt nur, wenn er im Dossier selbst eine Quellen-URL trägt: `{"wert": …, "quelle": "https://…"}` bzw. `quelle` am Listeneintrag (bei Teammitgliedern auch `openalex`). Es gibt keine Ersatzquellen. Das gilt auch für den Beschreibungstext, Rechtsform, Gründungsdatum, Finanzierungsmeldung und die Noise-Regeln. Ohne Beleg geht ein Kriterium mit 50 Punkten ein, steht in `evidence` als "keine Daten – neutral gesetzt" und in `offene_punkte`.
- **Ausnahme: vier Sourcing-Metadaten ohne URL.** `noise_class`, `match_confidence`, `in_databases` und `first_db_date` werden übernommen, weil sie das Ergebnis des Sourcing-Schritts selbst sind. In den Texten steht dann "laut Sourcing".
- **Branche** ist nur ein Label und bewegt keinen Score.
- **Confidence (0–1).** Anteil der belegten Kriterien nach Gewicht, multipliziert mit `match_confidence` aus dem Sourcing. Liegt `match_confidence` unter 0,5, steigt zusätzlich das Kriterium Datenlage im Risiko auf 90 Punkte. Ein Lead ganz ohne Zusatzdaten landet bei etwa 50 Punkten mit Confidence unter 0,1. Bitte in der Matrix nach `confidence` filtern oder einfärben, sonst sehen datenarme Leads wie Mittelfeld aus.
- **Harte Ausschlüsse.** `noise_class` ungleich `vc_potenzial` oder `stage = zu_spaet` deckelt `gesamt_score` auf 20. Der Grund steht in `ausschluss_grund`. Die drei Achsenwerte bleiben unverändert.
- **Evidence ohne URL** ist immer gekennzeichnet: neutrale Kriterien mit "keine Daten – neutral gesetzt", eine Stage-Regel ohne Beleg (z. B. "pre_gruendung: keine Rechtsform belegt – keine Daten, neutral gesetzt") ebenso, Sourcing-Metadaten mit "laut Sourcing (ohne URL)".
- **Pflichtangaben.** Fehlen Name, Beschreibungstext, ein datiertes Signal mit URL oder der Deutschland-Beleg, wird nicht bewertet: `status = zurueck_an_sourcing`, alle Scores sind leer, `confidence = 0,1`.
- **E-Mail.** Nur generische Postfächer (`info@`, `kontakt@` …) mit Quelle und auf der Domain der eigenen Website. Alles andere wird verworfen und die Spalte bleibt leer.

## Stage

| Wert | Regel |
|---|---|
| `zu_spaet` | belegte Finanzierungsmeldung, `noise_class = bereits_finanziert` oder belegtes Gründungsdatum älter als 36 Monate. Ist nur das Gründungsjahr bekannt, zählt der 31.12. Außerdem: Gründungsjahr aus Pressetext (`gruendungsjahr_hinweis`) älter als 36 Monate, **wenn bestätigt** durch eine belegte Kapitalgesellschaft oder `in_databases = true`. Ebenso: Datenbankprofil (`in_databases` + `first_db_date`) älter als 36 Monate, das höchstens 24 Monate vor dem ersten eigenen Signal liegt. Ein Datenbank-Eintrag allein reicht weiter nicht (Schalter `zu_spaet_wenn_in_databases`) |
| `pre_gruendung` | keine Kapitalgesellschaft belegt. Das gilt auch, wenn die Angabe fehlt, nicht mit GmbH, gGmbH, UG, AG oder SE endet (z. B. GbR, e.V., "AG Müller") oder eine Verneinung bzw. einen Plan enthält ("noch keine GmbH", "GmbH geplant") |
| `in_gruendung` | GmbH, gGmbH, UG, AG oder SE mit "i.G.", "i.Gr." oder "in Gründung" |
| `seed` | GmbH, gGmbH, UG, AG oder SE und belegter Reifegrad `pilot` oder `erste_kunden`. Kommt der Reifegrad aus der Textklassifikation (`reifegrad_quellen` von `to_dossier`), braucht er Fundstellen auf mindestens zwei Domains oder einen belegten Kunden/Piloten; sonst `pre_seed` mit Grund „Reifegrad … nur aus einer Quelle“, und `tech_reife` zählt nur als Proxy. Modellzitate zählen nicht. Handgepflegte Dossiers ohne `reifegrad_quellen` bleiben beim Einzelbeleg |
| `pre_seed` | GmbH, gGmbH, UG, AG oder SE sonst; oder belegtes Gründungsdatum ohne belegte Rechtsform; oder belegter `gruendungsjahr_hinweis` ohne belegte Rechtsform ("gegründet laut Quelle (Pressetext, JJJJ)", mit offenem Punkt "Gründungsjahr JJJJ nur aus Pressetext, nicht für Ausschluss verwendet" bzw. bei einem unbestätigten alten Jahr "… nicht durch Rechtsform oder Datenbankeintrag bestätigt – vor Kontakt prüfen") |

**Warum ein Pressetext-Jahr jetzt ausschließen darf (kiutra).** Ein Jahr aus einem Pressetext kann sich auf eine andere Firma beziehen. Zwei Prüfungen schützen dagegen: (1) Ein Jahr mehr als 24 Monate vor dem ersten eigenen Signal gilt weiter als Fremdbezug und wird ignoriert (Procado: Artikel von 2013, EXIST ab 2025). (2) Ein altes Jahr schließt nur aus, wenn die Firma unabhängig davon als bestehend belegt ist: Rechtsform aus dem Impressum oder ein Datenbankprofil. Dann ist die Wahrscheinlichkeit eines Namensvetters klein, und ein so belegtes Alter verletzt das HTGF-Kriterium „höchstens 3 Jahre“. Ohne Bestätigung (typisch: EXIST-Projekt vor der Gründung, Jahr aus einem Nebensatz) gibt es keinen Ausschluss, nur einen offenen Punkt. Ein Datenbankprofil allein schließt weiterhin nicht aus, ein über 36 Monate altes Profil, das zu den eigenen Signalen passt, dagegen schon („bereits bekannt“). Schalter: `zu_spaet_wenn_alter_hinweis_bestaetigt`, `zu_spaet_wenn_alter_db_eintrag`.

## Noise-Klasse

Liefert das Sourcing eine `noise_class`, gilt sie. Sonst greifen diese Regeln, jeweils nur mit Quelle am Feld:

| Wert | Regel |
|---|---|
| `bereits_finanziert` | belegte Finanzierungsmeldung |
| `agentur` / `beratung` | im `website_text` (Kontext-Evidence `website_text`) oder im belegten Beschreibungstext: mindestens zwei verschiedene, nicht verneinte Agentur-Wörter als ganze Wörter, davon mindestens ein Kernwort (Agentur, Beratung, Consulting, Webdesign …), und weniger Produkt-/Forschungswörter (Patent, Prototyp, Forschung, Sensor, Plattform …) als Agentur-Treffer. `beratung`, wenn mindestens die Hälfte Beratungs-Wörter sind. Ohne Website: Projekttitel endet auf ein Dienstleistungswort („…beratung“, „… Consulting“, „…agentur“, „…dienstleistung“). „Wir sind keine Agentur“ zählt nicht |
| `studi_projekt` | `repo_art` ist `kurs` oder `seminar` |
| `hobby` | `repo_art` ist `hobby`, oder: genau eine belegte Person, Rechtsform ausdrücklich `keine`, und weder Förderung noch Patent, Partner oder Papers belegt |
| `vc_potenzial` | sonst |

## Weitere Spalten

- `gruendungsjahr`, `gruendungsmonat`: belegtes Gründungsdatum, sonst ein belegter `gruendungsjahr_hinweis` (Jahr aus einem Pressetext, `{"wert": 2025, "quelle": …}`), sonst der Start einer belegten EXIST-Förderung. In beiden Ersatzfällen ist `gruendung_ist_proxy = true`. Ist nur das Jahr bekannt, bleibt der Monat leer. Ein Hinweis, der mehr als 24 Monate (`hinweis_max_vor_signal_monate`) vor dem ersten Signal liegt, wird ignoriert und als offener Punkt genannt.
- Als EXIST zählt nur ein Eintrag, dessen `programm` ein EXIST-Programmname ist (z. B. "EXIST-Forschungstransfer"), der ein Startdatum hat, nicht in der Zukunft beginnt und nicht länger als 12 Monate beendet ist. Fehlt das Enddatum, gilt eine Laufzeit von 36 Monaten. Nur exakt gleiche Einträge werden zusammengefasst; der SQLite-Lader fasst zusätzlich Signale mit demselben Förderkennzeichen zusammen.
- **Traktion** (`partner`, Final Gate M1): Verworfen werden Fördergeber, Programme und Behörden (Ministerium, EU, ESF/EFRE, EXIST, Projektträger …) sowie generische Phrasen („Global Partners“, „Our Customers“). An „und/and“ zerschnittene Namen werden über das Zitat wieder zusammengesetzt. Voll zählt ein Partner nur mit Rechtsform oder als bekannte Einrichtung, im Namen oder direkt dahinter im Zitat; sonst nur als Proxy. Muster: `katalog.partner_*`.
- `why_now` und Datenbankprüfung (M3): Ist die Quelle von `in_databases` `web.archive.org`, heißt es „kein archiviertes Crunchbase-/Dealroom-Profil (Wayback)“; nur bei einer echten Datenbanksuche „… nicht gefunden (Datenbanksuche)“. Bei einem Treffer: „bereits mit Datenbankprofil gelistet (Host) – Vorsprung prüfen“. Ohne Eintragsdatum ist `earliness_delta_monate` leer, dazu kommt ein offener Punkt; ein Treffer allein schließt weiterhin nicht aus.
- **Komplementäres Team** (Loop Runde 1): Jede Person trägt ihre Herkunft (`herkunft`/`herkuenfte`: impressum, linkedin, presse, website, kontext, sourcing) und `gruender`. Für n zählen Gründer und Geschäftsführung; „Teammitglied (…)“ zählt nur für den Mix. Mix belegt (`mehrere_mit_mix`, 1,0) = Tech und Business im Team, auch durch ein Teammitglied; die Aussage nennt Namen, Rollen und die Person mit Business-Profil (deren URL ist der Beleg), und die Hypothese führt das als Stärke. `mehrere_ohne_business` (0,5) nur, wenn **alle** Gründer einen ausdrücklich belegten Tech-Hintergrund haben (aus Rolle oder Ausbildung; ein „tech“ nur aus dem OpenAlex-Fallback „ab 5 Arbeiten“ zählt nicht, `hintergrund_quelle = openalex`) und niemand ein Business-Profil hat; dazu der offene Punkt „Business-Profil im Team nicht belegt – prüfen“. Fehlende Hintergründe ergeben „Mix unbekannt“ (0,6), nie einen Abzug. „solo“ (0,2) nur bei ausdrücklicher Angabe („Alleingründer“) oder in einem handgepflegten Dossier ohne Herkunft. Eine einzelne gefundene Person fällt sonst auf die Förderdaten zurück.
- **Datenbankbefund** (n2): `in_databases_quelle` ist bei einem Treffer immer eine Profil-URL (Datenbankprofil oder archivierter Profil-Snapshot), nie eine Such-URL. Hat nur Wayback einen Slug gefunden und die Datenbanksuche nichts, setzt `to_dossier` `in_databases_konflikt`. Dann steht in `why_now` „… Namensvetter prüfen“, dazu ein offener Punkt, und der Eintrag zählt weder als Bestätigung eines Gründungsjahrs noch für den Altersausschluss.
- **Website-VP** (n1): Kurze, wiederholte Menüzeilen, Überschriften im Title Case ohne Satzzeichen, zusammengeklebte Menüeinträge und weitere Handlungsaufforderungen („explore“, „discover“, „we are looking for“) fallen heraus. Bevorzugt wird ein Satz über das eigene Produkt („we develop …“, „our sensor …“) aus den ersten sechs.
- `name_gruender`: nur Personen mit Quelle. `to_dossier` übernimmt die Geschäftsführung aus dem Impressum (`managing_directors`, Beleg Impressum-URL, Rolle „Geschäftsführung“, `herkunft: impressum`), wenn context zu dieser Person kein Profil hat (Abgleich über den Namen). Kein Personenname wird verworfen: Ämter wie Rektor/Präsident, Registerangaben, „Product Development“, einzelne Wörter. Eine einzelne Geschäftsführerin gilt nicht als Solo-Gründerin; `komplementaer` fällt dann auf die Förderdaten zurück. Fehlt `works_in_field` (context setzt es bei Katalog-Leads bewusst nicht), zählt für `forscher_match` ersatzweise die Gesamtzahl der Publikationen eines OpenAlex-Profils mit `match_confidence` ≥ 0,5 als Proxy (ab 20: 0,8 · ab 5: 0,65 · ab 1: 0,55, gedämpft, ohne Malus).
- `evidence`: Liste aus `{dimension, kriterium, aussage, url, datum, punkte}`. `dimension` ist `team`, `marktpotenzial`, `risiko`, `stage` oder `noise`. In der CSV als JSON-Text in einer Zelle.
- `teilwerte`: Punkte, Gewicht und Beleg-Status je Kriterium.
- `earliness_delta_monate`: Monate vom ersten Signal bis zum ersten Datenbank-Eintrag, ohne Eintrag bis zum Stichtag. Liegt der Datenbank-Eintrag vor dem ersten Signal, ist der Wert 0. Ein Eintragsdatum nach dem Stichtag wird ignoriert.
- `produktbeschreibung` (erste zwei Sätze) und `value_proposition` (erster Satz): wörtlich aus dem Beschreibungstext, nur gekürzt. Ist der Beschreibungstext nur der Sourcing-Platzhalter („„X“ – Projekt im Programm …“), kommen beide **extraktiv aus dem belegten `website_text`**. Es zählen nur inhaltliche Sätze: ab 6 Wörtern, ohne Seitentitel, Navigation, Versalien-Zeilen, Cookie-/Rechtstext, Förderhinweis, Handlungsaufforderung und Baukasten-Blindtext („Lorem ipsum“); ein kurzer erster Satz bekommt den zweiten angehängt (≤ 200 Zeichen). Ohne Website-Text werden sie aus der Katalogseite gebaut: Titel, Programm, Lehrstuhl/Institut, Summe, Laufzeit, Fachgebiets-Hinweis, dazu „Produkt und Zielkunde sind noch nicht belegt“. Ohne Förderende im Pre-Gründungsstadium nennt die Hypothese „Wenn bis Förderende MM/JJJJ die Gründung gelingt, …“, `why_now` eine laufende Förderung („… läuft bis MM/JJJJ“) oder eine lange beendete („… lief bis MM/JJJJ – Status prüfen“). `investmenthypothese` und `why_now`: aus belegten Kriterien und den vier Sourcing-Metadaten zusammengesetzt. `why_now` nennt das Ende einer EXIST-Förderung, wenn es höchstens 12 Monate in der Zukunft liegt ("… endet MM/JJJJ") oder schon vorbei ist, solange die Förderung noch zählt ("… endete MM/JJJJ"). Am Ende steht das Alter des jüngsten Signals ("jüngstes Signal in diesem Monat", "… vor 1 Monat", "… vor 5 Monaten"). Das Kriterium bisherige Förderung nennt die Programme, z. B. "Bisherige Förderung 135.000 EUR (EXIST-Gründungsstipendium)". Bei einem Ausschluss lautet die Hypothese "Kein Investment-Case: …", bei Confidence unter 0,4 "Datenlage zu dünn für eine Hypothese (Confidence …). Belegt: …" mit den stärksten belegten Kriterien. Es formuliert kein Sprachmodell.
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
| belegte Aussagen | `score_drivers`; Risikokriterien unter `texte.risiko_ab` (50 Punkte) als "Risikomindernd: …" |
| belegte Risikokriterien ab 50 Punkten, Ausschlussgrund | `risks` |
| `offene_punkte` | `open_questions` |

## Offen

- Die Gewichte sind nicht kalibriert. Dafür fehlen noch 10 von Hand bewertete Leads.
- Echte Leads gibt es: Das Sourcing liefert 733 EXIST-Projekte aus dem Förderkatalog (Beispiel `examples/sourcing/sample_dossiers.json`; vier weitere angereicherte Vorhaben in `examples/context/real_dossiers.json`, deren Scores in `examples/context/scores/`). Der Kontext-Schritt liefert Rechtsform, Förderung, Papers je Gründer, IP, Partner und Produkttyp mit Quellen (`context/ENRICHMENT.md`); `evaluation/engine.py` reicht sie durch.
- Leads, die nur aus dem Förderkatalog stammen, liegen nach der Kalibrierungsrunde bei 47,1 bis 58,2 (Offline-Lauf über 733, Median 54,1, 89 verschiedene Werte; vor T2 48,7 bis 53,7 mit 6 Werten). Der Timing-Abschlag von 15 % auf 5 % verengt die Offline-Spanne bewusst: Offline-Unterschiede kamen vor allem aus dem Förderende. Rund die Hälfte des Gewichts bleibt ohne Website, Gründer und Papers neutral, das begrenzt die Spreizung. Gleiche Katalogprofile (z. B. Gründungsstipendium, TUM-Informatik, Gründungsfenster) bleiben gleich. Gleichstände bricht nicht das Scoring, sondern Pipeline und Dashboard über die Schritt-1-Priorität (`ranking_key` in `pipeline.py`).
- Stipendien-Rechnung: Kinderzuschlag 150 EUR und Sachmittel 30.000 EUR sind belegt (BMWE-Onepager 2025). 3.000 EUR/Monat für Promovierte und 5.000 EUR Coaching sind **Annahmen**, die noch am Richtlinientext (BAnz. 18.04.2023) zu prüfen sind. Die Rechnung bleibt eine Untergrenze, solange die echten Sätze nicht höher liegen. Ändert sich die Richtlinie, sind die Werte in `katalog` anzupassen. Die **Demo-Leads** des Dashboards landen weiter bei drei Gesamtscores (50,0 / 52,4 / 54,2).
- Die Textklassifikation (Reifegrad, Produkttyp, Regulatorik, Partner) ist die schwächste Quelle: im ersten Faktencheck waren rund zwei Drittel ihrer Werte falsch oder schwach belegt, vor allem durch Pressemeldungen über andere Firmen. Harte Quellen (Impressum, Förderkatalog, Wayback, OpenAlex) stimmten in über 90 % der Fälle.
- Der Dashboard-Weg nimmt als Signale nur die Schritt-1-Signale, Wayback-Erstaufnahmen und datierte Evidence der Felder `grants`, `idw` und `founding_year_mention`. Datenbanktreffer (`in_databases`, `first_db_date`), idw-Erwähnungen (`idw_mention`, Quelle "idw (Erwähnung)"), `*_alt`-Kandidaten und Modellzitate ("Ollama-Zitat …") zählen nicht. Hat Schritt 1 die Branche nicht klassifiziert (`htgf_sector` leer und Marker `industry_unclassified` bzw. "Branche nicht klassifiziert"), bleibt `branche` leer. `ScoringInput.public_grant` wird nicht übernommen; die Förderung kommt allein aus `lead.grants`.
- Der Dashboard-Weg übersetzt `product_stage` und `funding_stage` nur bei exakter Übereinstimmung mit einer festen Liste (siehe `evaluation/engine.py`) und nur mit passendem Evidence-Eintrag.
- Ein Sprachmodell für weiche Kriterien ist nicht eingebaut.
- Der SQLite-Lader übernimmt eine Fördersumme aus einem Signal mit eindeutigem Betrag in deutscher Schreibweise. Ein Förderkatalog- oder Impressums-Signal benötigt eine ausdrückliche Ortsangabe in Deutschland, damit es als Deutschland-Beleg gilt.
- Die Agentur-Regel erkennt keine Verneinung ("Wir sind keine Agentur und bieten keine Beratung" gilt als Beratung).
- `lead_id` wird bereinigt (Steuerzeichen zu Leerzeichen, höchstens 120 Zeichen). Ein Dossier ohne `lead_id` und ohne lateinischen Namen bekommt eine Hash-ID.
- Bei einem Ordner als Input wird eine unlesbare Datei mit Warnung übersprungen.
- Ob eine Quelle die Aussage wirklich stützt, prüft das Scoring nicht. Es prüft nur, dass das Sourcing zu jedem Fakt eine Quelle mitliefert.
- Datenarme Leads liegen bei rund 50 Punkten und damit über ausgeschlossenen Leads (maximal 20).
