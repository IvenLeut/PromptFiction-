# FounderRadar · Kontext für das Startup-Screening

Wir entwickeln FounderRadar in einem vierköpfigen AI-Hackathon-Team für den High-Tech Gründerfonds (HTGF). Das Tool entdeckt Pre-Seed- und Seed-Kandidaten mit möglichem HTGF-Fit und bereitet die aussichtsreichsten für eine quantitative Bewertung vor. Das Projekt sucht in den Kategorien Digital Tech, Industrial & Deep Tech, Climate Tech, Life Sciences sowie Chemie & Materialien. [HTGF](https://www.htgf.de/)

Der Arbeitsauftrag für das Sourcing-Modul reicht von der branchenspezifischen Suche bis zur vollständigen UI-Ergebnisliste mit Quellenbelegen.

## Aufnahmekriterien für die UI-Ergebnisliste

Gib jedes eindeutig identifizierte Startup aus den durchsuchten Quellen aus, das alle drei Kriterien erfüllt und für das nach dem Datenabgleich alle sieben Ausgabefelder belegt vorliegen. Jedes Unternehmen erscheint einmal.

- **Branche.** Das Unternehmen entspricht der aktuell in der UI ausgewählten Branche. Eine belegte Produktbeschreibung oder der Unternehmensgegenstand stützt die Zuordnung.
- **Deutschland.** Das Unternehmen wurde in Deutschland gegründet und hat hier seinen belegten Sitz. Setze `country="DE"` erst, wenn ein Registereintrag, ein Unternehmensimpressum oder eine vergleichbar belastbare Quelle den Sitz des konkreten Unternehmens bestätigt. Hinterlege den Sitzbeleg in `country_evidence` und prüfe die Gründung in Deutschland anhand einer Quelle, die sich auf die Gründung bezieht. Eine `.de`-Domain, eine deutschsprachige Website, ein persönlicher Wohnort oder eine deutsche Niederlassung eines ausländischen Unternehmens reichen als Beleg nicht aus.
- **Gründungszeitraum.** Die Gründung liegt innerhalb des konfigurierten Zeitfensters. Der Standard für den ersten Build reicht vom Datum drei Jahre vor dem Suchlauf bis zum Laufdatum, jeweils einschließlich. Das orientiert sich an der veröffentlichten Altersgrenze des HTGF. Für die Altersprüfung reicht ein belegter Gründungsmonat ohne Tagesangabe, sofern der ganze Monat innerhalb des Fensters liegt. Überschneidet er die Grenze, bleibt der Fall bis zur Klärung offen. [Investmentkriterien des HTGF](https://www.htgf.de/)

Teams vor der Gründung und Treffer mit fehlenden oder widersprüchlichen Pflichtangaben bleiben interne Prüffälle. Suche gezielt auch nach kleinen Teams und Startups mit wenig öffentlicher Präsenz. Mitarbeiterzahl, Finanzierung, Pressepräsenz, GitHub-Aktivität und zusätzliche Frühphasensignale sind keine Pflichtangaben.

## Quellenagenten und Suchabdeckung

- Weise jeder konkreten Datenquelle pro Suchlauf einen eigenen Subagenten zu. GitHub, Show HN und jedes ausgewählte regionale Verzeichnis erhalten beispielsweise jeweils einen eigenen Agenten. Python koordiniert die Aufträge. Alle Agenten bekommen dieselbe UI-Branche, dieselben Deutschlandkriterien, dasselbe Gründungsfenster und dasselbe Ausgabeformat.
- Jeder Agent sucht unabhängig in seiner Quelle. Verteile unterschiedliche Quellen und unabhängige Abfragen parallel im Rahmen der verfügbaren Kapazität. Der Agent speichert pro Fund Kandidatenname, Meldungsdatum, Quellen-URL, kurzen Textausschnitt, gefundene Feldwerte und zugehörige Belege. Er gibt auch Teiltreffer zurück, damit der zentrale Abgleich sie mit Funden anderer Agenten ergänzen kann.
- Zerlege die ausgewählte Branche in Teilgebiete, Technologien, Anwendungen und Zielkunden. Nutze deutsche und englische Suchbegriffe und Synonyme. Verteile die Suche über das gesamte konfigurierte Gründungsfenster und bundesweit. Kombiniere überregionale Quellen mit regionalen Gründungszentren, Förderlisten, Hochschulen und lokalen Startup-Verzeichnissen, damit auch wenig sichtbare Unternehmen gefunden werden.
- Verarbeite alle verfügbaren Ergebnisseiten. Teile große Abfragen nach Region, Zeitraum oder Teilbranche auf, sofern die Quelle das unterstützt. Speichere Funde und Fortschritt, damit ein Lauf fortgesetzt werden kann und bei kurzlebigen Feeds eine Historie entsteht. Erfasse je Quelle, welche Bereiche abgedeckt wurden, wie viele Funde zurückkamen und wo Abrufe ausstehen oder gescheitert sind.

## Screening-Ablauf

Quellenagenten sammeln unabhängig. Qwen klassifiziert und extrahiert. Python führt die Funde zentral zusammen, validiert die Belege und entscheidet über die Aufnahme in die UI-Liste.

1. **Breit in der UI-Branche suchen.** Die gewählte Branche steuert die Abfragen der Quellenagenten. Für Software gehören GitHub und Show HN ebenso zur Suche wie regionale Gründungsquellen. Für die übrigen Sektoren gehören unter anderem Förderbekanntmachungen, Ausgründungslisten und Meldungen von Industriepartnern dazu. Nutze registerbasierte Datensätze zur Entdeckung, sofern ein geeigneter Zugang verfügbar ist.
2. **Funde zentral zusammenführen und eindeutige Ausschlüsse anwenden.** Ordne die Treffer anhand einer eindeutigen Registerkennung oder einer belegten Verbindung von Firmenname, Sitz und offizieller Domain derselben Firma zu. Ein Produktname, eine gemeinsam genutzte Domain oder ein ähnlicher Firmenname allein genügt nicht. Bei unsicherer Zuordnung bleiben die Funde bis zur Klärung getrennt. Python sortiert anhand vorhandener Belege eindeutig branchenfremde, ausländische oder zu alte Unternehmen aus. Das Meldungsdatum dient höchstens der Verarbeitungsreihenfolge. Für die Altersprüfung zählt das Gründungsdatum.
3. **Branche der übrigen Kandidaten bestätigen.** Verwende eindeutige Belege direkt. Bei offenen Zuordnungen klassifiziert Qwen lokal über Ollama anhand relevanter Ausschnitte. Die strukturierte Antwort enthält Technologie und Anwendung als gemeinsames Feld sowie HTGF-Sektor, ein optionales frühes Signal und einen wörtlichen Beleg. Python validiert das Schema und prüft, ob das Zitat im Ausschnitt steht. Ein Cache verwendet die Klassifikation für denselben Text bei gleicher Modell- und Prompt-Version wieder. [Ollama – strukturierte Ausgaben](https://docs.ollama.com/capabilities/structured-outputs)
4. **Gründung und Sitz in Deutschland belegen, dann das Alter prüfen.** Nutze zuerst die Belege aus allen zusammengeführten Funden. Prüfe bei Bedarf weitere Aussagen zum selben Unternehmen. Bestätige Gründung und Sitz in Deutschland und vergleiche das belegte Gründungsdatum mit dem konfigurierten Zeitfenster.
5. **Pflichtfelder abgleichen und fehlende Angaben gezielt recherchieren.** Übernimm belegte Werte feldweise aus den Funden desselben Unternehmens. Bei Widersprüchen prüfe, welche Quelle für das konkrete Feld und den richtigen Sachverhalt maßgeblich ist. Ein Registerbeleg kann etwa den heutigen Sitz belegen, während eine Gründungsmeldung den Gründungsmonat belegt. Für Gründer:innen und Kontaktangaben nutze überprüfbare Unternehmensangaben. Gleichwertige, widersprüchliche Belege bleiben bis zur Klärung intern. Recherchiere fehlende Felder gezielt anhand weiterer Quellen.
6. **Alle bestätigten und vollständigen Unternehmen ausgeben.** Zeige eine Zeile je Unternehmen mit allen sieben Pflichtfeldern und gültigen Aufnahmebelegen. Bei Paginierung bleiben sämtliche bestätigten Treffer zugänglich. Weise die Abdeckung der tatsächlich durchsuchten Quellen und die Anzahl interner Prüffälle aus.

Die Outline nennt `vc_sourcing.py` als vorhandenen Startpunkt für GitHub und Show HN. Die Datei fehlt im aktuellen Checkout. Vor der Integration den Branch oder Pfad klären. Der Einstiegspunkt in diesem Branch ist `sourcing.engine.search(criteria: SearchCriteria) -> list[RawLead]` und der echte Anbieter ist hier noch ein Platzhalter.

## Ergebnisliste und Schnittstelle

Die UI-Ergebnisliste enthält eine Zeile pro passendem Unternehmen. Alle sieben Felder sind Pflichtfelder.

| Feld | Erfassung |
| --- | --- |
| Gründer:innen | Namen als belegte Liste. Die Quelle muss die Personen als Gründer:innen des Unternehmens identifizieren. |
| E-Mail | Öffentlich angegebene geschäftliche Kontaktadresse des Unternehmens, bevorzugt die offizielle allgemeine Kontaktadresse. |
| Unternehmensname | Belegter Name des konkreten Unternehmens. |
| Unternehmenswebsite | Offizielle Website als URL. |
| Branche | Kategorie für den Dashboard-Filter. Verwende Branchen-Keywords zur Suche und ordne den Treffer anhand von Produktbeschreibung oder Unternehmensgegenstand zu. |
| Gründungsmonat | Belegter Monat als Zahl von 1 bis 12. Ist bisher nur das Jahr bekannt, bleibt der Treffer bis zum Nachweis des Monats intern. |
| Gründungsjahr | Belegtes Jahr der Unternehmensgründung. Das Datum einer Patentanmeldung, eines Produktstarts oder eines Registereintrags braucht eine ausdrückliche Bestätigung als Gründungsdatum. |

Halte pro Angabe die Quellen-URL und die relevante Aussage fest. Verschiedene Pflichtfelder dürfen aus unterschiedlichen Quellen stammen, wenn die Zuordnung zum selben Unternehmen belegt ist. E-Mail-Adressen und fehlende Datumsteile werden nicht aus Namen, Domains oder Datumsformaten abgeleitet.

Der bestehende Pipeline-Vertrag liefert `list[RawLead]`. `pipeline.discover` prüft derzeit Sitzbeleg und Branche, dedupliziert nach ID und bricht beim Trefferlimit aus `SearchCriteria` ab. Für die vollständige UI-Liste muss der Suchlauf alle verfügbaren Treffer verarbeiten und das aktuelle Limit durch eine vollständige Ausgabe oder Paginierung ersetzen. Die Zuordnung der fünf Suchkategorien zu `Industry` braucht eine Teamentscheidung. `Industry` enthält derzeit unter anderem `FinTech` und hat keine eigene Kategorie für Chemie & Materialien.

`RawLead` enthält bereits Unternehmensname, Branche, Fundquelle und Sitzbeleg. `EnrichedLead` führt Website, Gründer:innen und `founded_on` als vollständiges Datum. Der Screening-Vertrag muss alle sieben Pflichtfelder und ihre Belege bereits vor der UI-Ausgabe transportieren. Dazu gehört die Unterstützung von belegtem Gründungsmonat und Gründungsjahr ohne bekannten Tag. Änderungen am gemeinsamen Datenvertrag in [`models.py`](../models.py) werden mit dem Team abgestimmt.

## Quellen

| Quelle | Vorgehen und Machbarkeit |
| --- | --- |
| Patentdatenbanken | Recherchiere nach Technologiebegriffen oder Patentklassen in DEPATISnet. Prüfe den Anmelder oder Inhaber und ordne das Patent bei eindeutiger Zuordnung einem Unternehmen zu. Erfinderrolle und Gründerrolle brauchen eigene Belege. Der automatisierte Abruf über DPMAconnectPlus setzt eine Anbindung mit Anschlussgebühr voraus. [DPMA-Recherche](https://www.dpma.de/en/ip-search/databases/depatisnet) · [DPMAconnectPlus](https://www.dpma.de/recherchieren/datenabgabe/dpmaconnectplus) |
| Unternehmensregister | Nutze branchenbezogene Keywords in den dafür verfügbaren Suchbereichen und prüfe den Unternehmenssitz im konkreten Treffer. Die Suchbereiche decken unterschiedliche Daten ab. Bestimmte Dokumentabrufe erfordern eine Sicherheitsabfrage. Für solche Abrufe kommen im MVP eine manuelle Prüfung oder ein freigegebener Datenzugang infrage. [Suchhilfe des Unternehmensregisters](https://www.unternehmensregister.de/de/so-gehts/suche?dest=ureg&language=de) |
| Studentische Organisationen mit Gründungsbezug | Prüfe veröffentlichte Startup- und Alumni-Listen oder Beiträge zu Pitch-Veranstaltungen, etwa bei START Munich. Verifiziere bei jedem Hinweis separat, ob das Unternehmen bereits gegründet ist und seinen Sitz in Deutschland hat. [START Munich](https://www.startmunich.de/) |
| Forschungsinstitute | Nutze veröffentlichte Ausgründungslisten und Technologietransfer-Meldungen, etwa bei Fraunhofer ISE. Ein Institut kann mehrere Ausgründungen nennen, deren Sitz und Branche jeweils einzeln geprüft werden. [Fraunhofer ISE – Ausgründungen](https://www.ise.fraunhofer.de/de/ueber-uns/spin-offs.html) |
| Öffentliche Förderbekanntmachungen | Suche nach namentlich genannten Teams oder Unternehmen und konkreten Projektinformationen. Prüfe im Einzelfall, was die Meldung tatsächlich belegt, etwa eine Förderzusage oder einen Projektstart. |
| Regionale Gründungsnetzwerke und Verzeichnisse | Durchsuche die öffentlichen Startup-Listen und Meldungen von Gründungszentren, Hochschulen und regionalen Förderprogrammen. Beziehe kleinere Standorte und spezialisierte Programme ein. |
| Industriepartner | Nutze öffentliche Meldungen zu Piloten, Kooperationen oder Industrietests. Achte darauf, ob ein Test angekündigt, begonnen oder bereits abgeschlossen wurde. |
| GitHub | Suche bei passender Branche nach aktiven öffentlichen Repositories und Profilen. Relevante Beiträge oder Releases sind Hinweise auf ein Projekt. Für einen Treffer braucht es eine belegbare Verbindung zwischen dem Projekt und einem deutschen Unternehmen. [GitHub REST API – Events](https://docs.github.com/en/rest/activity/events) |
| Show HN | Rufe aktuelle Beiträge über die offizielle Hacker-News-API (`/v0/showstories`) ab. Folge dem Produktlink und prüfe Unternehmen, Sitz und Branche. Der Feed liefert bis zu 200 aktuelle Beiträge. [Offizielle Hacker-News-API](https://github.com/HackerNews/API#ask-show-and-job-stories) |

## Erster Screening-Build

Starte mindestens zwei Quellenagenten mit derselben Suchanfrage. Prüfe, dass ergänzende Angaben aus zwei Quellen für dasselbe Unternehmen zu genau einer vollständigen Zeile zusammengeführt werden. Prüfe auch, dass ein fehlender Gründungsmonat, eine nicht belegte E-Mail oder ein ungeklärter Widerspruch den Treffer intern hält. Ein Testlauf mit mehr als 30 vollständigen und passenden Unternehmen muss alle Treffer ausgeben.

## Offene Fragen zum Screening

- Wie bilden wir die fünf Suchkategorien im Dashboard ab, insbesondere FinTech und sektorübergreifende Kandidaten?
- In welchem Branch oder unter welchem Pfad liegt `vc_sourcing.py`?

## Machbarkeit bei jeder Aufgabe offen benennen

Wenn eine Idee technisch nicht umsetzbar ist oder mit den verfügbaren Daten, Zugängen oder der Hackathon-Zeit nicht zuverlässig funktioniert, sage das direkt. Nenne den konkreten Grund und zeige eine umsetzbare Alternative. Wenn eine Voraussetzung noch geprüft werden muss, kennzeichne die Idee als offen. Weise bei unvollständiger Quellenabdeckung darauf hin, welche Treffer der aktuelle Stand zuverlässig liefern kann.

## Kontext für die nachgelagerten Module

Die nachgelagerten Module nutzen die vollständige Screening-Ergebnisliste samt Belegen. Für die vertiefte Recherche ist eine `shortlist.json` mit bis zu fünf priorisierten Kandidaten vorgesehen. Ein belegtes Signal wie ein laufender Pilot oder ein bestätigter Industrietest kann dabei den Kontaktgrund liefern. Meldungsdatum, Quellen-URL und Textbeleg machen den Grund nachvollziehbar.

Die Vertiefung ergänzt Angaben zum Team, zum Produkt, zum Markt und zur Finanzierung. Danach nutzt die Bewertungsstufe diese Angaben für eine Scorecard oder die VC Method. Ein geplanter Python-Adapter übergibt belegte Eingaben und Teamannahmen an die Bewertungsbibliothek. Offene oder widersprüchliche Angaben können als Fragen ins Erstgespräch einfließen. [Startup Valuation Engine](https://github.com/simonmak-ascent/startup-valuation)
