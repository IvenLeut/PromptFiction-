# Datenübergabe an Schritt 3

Das Live-Scoring erhält pro Lead genau ein Objekt vom Typ `ScoringInput`.
Es gibt `EvaluationScores` zurück. Die Pipeline verbindet diese mit dem Dossier
für das Dashboard. Die Demo verwendet weiterhin ihre vorkonfigurierten Scores.
Die Live-Bewertung steht in `evaluation/engine.py` (Regeln in `scoring/`, siehe `scoring/SCORING.md`):
`evaluate(scoring: ScoringInput | EnrichedLead, *, lead: EnrichedLead | None = None, as_of=None)`.
Die Pipeline (`pipeline.evaluate_context`) übergibt neben dem `ScoringInput` das Dossier als `lead=`, weil
der ScoringInput keine Gründerprofile, Förderbeträge, Rechtsform, Partner oder Patente enthält. Nutzbare
ScoringInput-Parameter haben Vorrang. Der Aufbau des ScoringInput liegt in `scoring_input.py`
(`build_scoring_input`; vorher `scoring.py`, umbenannt, weil `scoring/` das Paket der Bewertung ist).

Vor der Bewertung hält die Pipeline einen Lead als `issue` zurück (`scoring_input.admission_issue`,
die einzige Stelle dieser Regel), wenn am Stichtag kein nutzbarer
Deutschland-Beleg vorliegt (`country.status != "usable"`) oder wenn `vc_status` den Wert `confirmed` oder
den Status `conflicting` hat. Ein unbekannter VC-Status (Status `missing` oder `ambiguous`)
ist bei Forschungsprojekten der Normalfall und wird ebenso bewertet wie der Wert `reported_none`.

## Export und Reproduktion

~~~bash
python -m context examples/scoring-leads.json dossier.json --offline --as-of 2025-12-31 --scoring-output scoring.json
python -m context dossier.json replay.json --replay
~~~

`scoring.json` und `replay.json` enthalten eine nach Lead-ID sortierte Liste.
Der Replay verwendet die Stammdaten und die im Dossier gespeicherten
`scoring_sources`. Diese enthalten die für Schritt 2 erfassten Quellenausschnitte
einschließlich mitgelieferter Signale und abgerufener Seiten. Bei alten Dossiers
dienen die ursprünglichen `signals` als Fallback. Für Marktzahlen werden die
strukturierten Recheneingaben, Originalbelege und Jahresreihen erneut ausgewertet.
Die bereits exportierten Parameterwerte und abgeleiteten Marktzahlen werden
beim Replay und vor dem Live-Scoring neu berechnet.

`schema_version` identifiziert das Datenformat. `rules_version` identifiziert
Parser und Rechenregeln. Vergleichbar sind Läufe mit demselben Quellensnapshot,
denselben Stammdaten und Markteingaben, derselben Regelversion und demselben
Stichtag. Der Replay übernimmt den exportierten Stichtag. `--as-of` kann ihn
überschreiben. Der Stichtag begrenzt datierte Quellen, zukünftige Gründungsdaten
und Jahresangaben. Aus undatierten Quellen lässt sich keine historische
Verfügbarkeit ableiten. Ohne Stichtag werden die vorhandenen Angaben ausgewertet.
Ein erneuter Live-Abruf kann die Eingaben ändern.

Ein Beleg ist über einen SHA-256-Hash seines Inhalts referenziert. Die ID umfasst
Lead-ID, URL, normalisierten Quellenausschnitt, Dokumentdatum und Herkunftstyp.
Der Export sortiert Belege nach ID und Kennzahlen nach Bezugsjahr. Flüchtige
Abrufzeitpunkte stehen im Dossier. Das ausführliche Dossier enthält auch optionale
Qwen-Zitate. An der Scoring-Schnittstelle wird ausschließlich aus den
eingefrorenen Quellen und den expliziten Markteingaben gelesen.

## Parameter und Regeln in Version 1.0

| Parameter | Typ und Einheit | Zulässige Quelle und Regel |
| --- | --- | --- |
| `country` | `DE` | Übernommener Deutschland-Beleg. Der Status gibt an, ob ein nutzbarer Beleg vorliegt. |
| `founded` | Jahr, optional Monat und Tag. Genauigkeit `year`, `month` oder `day` | Explizites Gründungsdatum. Kompatible Teilangaben lassen die genaueste belegte Angabe zu. Nur im Sourcing genannte Daten sind `informational`. |
| `product_stage` | `idea`, `paper`, `lab_prototype`, `prototype`, `mvp`, `pilot`, `first_customers`, `commercial` | Explizite Angabe zur Produktreife, normalisiert über eine feste Liste. |
| `vc_status` | `confirmed` oder `reported_none` bei nutzbarer Angabe | Expliziter VC-Status oder typisierte Angabe aus Schritt 1. `missing` mit `null` bedeutet unbekannt. Der Live-Pfad hält nur den Wert `confirmed` und den Status `conflicting` zurück; unbekannte Angaben werden bewertet. |
| `public_grant` | `applied`, `approved`, `received`, `none_reported` | Expliziter Förderstatus. Ein Antrag oder eine Bewilligung verändert den VC-Status nicht. Abweichende Statusangaben bleiben ohne eindeutige Zuordnung offen. |
| `completed_rounds`, `planned_round` | `pre_seed`, `seed`, `series_a`, `series_b`, `series_c`, `other` | Explizit abgeschlossene Eigenkapitalrunde oder explizit geplante Runde. Die Liste dokumentiert belegte Phasen und dient nicht als Zähler einzelner Abschlüsse. |
| `round_size_eur_cents`, `asking_pre_money_eur_cents` | Positive Ganzzahl in EUR-Cent | Explizit beschrifteter Betrag und EUR/€. Für die separate VC-Methode müssen beide Angaben ein gemeinsames Quelldokument referenzieren. |
| `annual_revenue_eur_cents` | Ganzzahl in EUR-Cent, je Bezugsjahr | Expliziter Jahresumsatz mit Jahr und EUR/€. Belegter Nullumsatz ist die JSON-Zahl `0`. |
| `annual_customer_count`, `annual_paying_customer_count` | Ganzzahl je Bezugsjahr | Explizit ausgewiesene Kundenzahl bzw. Zahl zahlender Kunden. Referenzen, LOIs, Piloten und Forschungspartner bleiben getrennte Dossierangaben. |
| `annual_revenue_growth_pct` | Dezimalzahl in Prozent, je Bezugsjahr | Explizites Jahreswachstum mit Prozentzeichen. |
| `tam`, `sam`, `som` | Dezimalzahl je Jahr mit Währung, Geografie und Periode | Geprüfte Kundenzahl und Jahrespreis für denselben Markt. SAM nutzt einen erreichbaren Anteil, SOM zusätzlich die Kapazität. Kundenanteile werden auf ganze Kunden abgerundet. |
| `market_growth[].cagr` | Dezimalzahl in Prozent pro Jahr mit Start- und Endjahr | Vergleichbare, explizit geprüfte Jahreswerte. Die Ausgabe rundet bei üblicher Größenordnung auf sechs Nachkommastellen mit Half-Even. Beobachtete und prognostizierte Reihen werden separat verarbeitet. |

Für Unternehmensangaben akzeptiert der Parser explizite Feldbezeichnungen
oder unterstützte Überschrift-Wert-Paare. Die Quellenzuordnung erfolgt über
`subject_lead_id`, eine explizite Zeile wie `Unternehmen: Beispiel GmbH` oder
die zur Lead-Website passende Domain. Eine ausdrücklich abweichende
Unternehmenszuordnung schließt das Signal aus. Erkannte Angaben ohne
Zuordnung ergeben `ambiguous`. Eine bestätigte Textfundstelle gibt wieder,
was die Quelle berichtet. Sie bestätigt die Aussage nicht unabhängig.

Geldbeträge werden ohne Rundung in Cent überführt. Eindeutige Gruppierung
mit Leerzeichen, mehrfache gleichartige Tausendertrennzeichen und gemischte
Gruppierung plus Dezimalzeichen sind zulässig. Ein einzelnes Komma oder
ein einzelner Punkt mit genau drei Folgeziffern bleibt mehrdeutig.
Dezimalwerte in abgeleiteten Parametern werden als JSON-Strings serialisiert.

Marktparameter verwenden explizit als `source_reviewed` deklarierte Belege.
Für Annahmen können zusätzlich als `assumption` deklarierte Belege verwendet
werden. TAM, SAM und SOM bleiben Schätzungen bzw. Szenarien. Die bestehenden
Vergleichstransaktionen und Multiples verbleiben im Dossier. Sie stehen
für diesen Vertrag erst nach Festlegung eines eigenen Scoring-Parameters
zur Verfügung.

## Status und Beispiel

- `usable` erlaubt die Verwendung des Werts für den jeweiligen Zweck. Bei
  Angaben aus Schritt 1 bezeichnet `upstream_reported` die Herkunft.
- `missing` bedeutet, dass keine ausreichend gestützte Angabe vorliegt.
- `ambiguous` bezeichnet eine erkannte Angabe mit unklarem Format oder
  unklarer Zuordnung.
- `conflicting` enthält die Belege für abweichende Angaben zum selben Wert
  und Zeitraum. Der Wert bleibt `null`.
- `informational` enthält einen Wert samt Herkunft für die Einordnung.
  Schätzungen, Prognosen und Szenarien sind in diesem Vertrag keine
  Scoring-Eingaben.

Die Datei [scoring-leads.json](examples/scoring-leads.json) enthält einen
expliziten Pilotstatus, einen Nullumsatz für 2023 und zwei abweichende
Umsatzangaben für 2024. Der Export enthält entsprechend `pilot / usable`,
`0 / usable` und `null / conflicting` mit zwei Beleg-IDs. Das
[JSON-Schema](examples/scoring-input-schema.json) beschreibt den Block und
die vollständige Exportstruktur.
