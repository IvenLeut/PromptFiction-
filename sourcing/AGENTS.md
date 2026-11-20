# FounderRadar · Kontext für das Startup-Screening

Wir entwickeln FounderRadar in einem vierköpfigen AI-Hackathon-Team für den [High-Tech Gründerfonds (HTGF)](https://www.htgf.de/). Die Anwendung soll junge Startups mit Erfolgspotenzial finden und bewerten. Dieses Verzeichnis verantwortet die Suche nach Unternehmen und die Übergabe belegter Kandidaten an die weitere Pipeline. Die Bewertung von Erfolgspotenzial und Frühphaseneignung sowie das Ranking erfolgen in der Bewertungsstufe.

## Nur Unternehmen aus Deutschland

- Gib ausschließlich bestehende Unternehmen mit belegtem Sitz in Deutschland aus. Setze `country="DE"` erst, wenn ein Registereintrag, ein Unternehmensimpressum oder eine vergleichbar belastbare Quelle den Sitz des konkreten Unternehmens bestätigt. Hinterlege den Beleg in `country_evidence`.
- Bei unklarem oder widersprüchlichem Sitz bleibt der Kandidat bis zur Klärung aus der Ergebnisliste. Eine `.de`-Domain, eine deutschsprachige Website, ein Wohnort im GitHub-Profil oder eine deutsche Niederlassung eines ausländischen Unternehmens reichen jeweils als Sitzbeleg für das Unternehmen nicht aus.
- Ein Team, Forschungsprojekt oder Open-Source-Repo kann zur Entdeckung führen. Für die Ergebnisliste muss daraus ein konkretes, bereits gegründetes Unternehmen mit Deutschlandbeleg hervorgehen.

## Ergebnisliste und Schnittstelle

Die Gesamtausgabe enthält eine Zeile pro Unternehmen. Folgende Felder sind für die Ergebnisliste vorgesehen.

| Feld | Erfassung |
| --- | --- |
| Gründer:innen | Belegte Namen als Liste. Bei fehlenden Angaben bleibt die Liste leer. |
| E-Mail | Öffentlich angegebene geschäftliche Kontaktadresse, bevorzugt die offizielle Unternehmensadresse. Bei fehlendem Beleg bleibt das Feld leer. |
| Unternehmensname | Belegter Name des konkreten Unternehmens. |
| Unternehmenswebsite | Offizielle Website als URL. |
| Branche | Kategorie aus `Industry` für den Dashboard-Filter. Verwende Branchen-Keywords zur Suche und ordne den Treffer anhand von Produktbeschreibung oder Unternehmensgegenstand zu. |
| Gründungsmonat | Belegter Monat als Zahl von 1 bis 12. Bleibt unbekannt, wenn die Quelle nur das Jahr nennt. |
| Gründungsjahr | Belegtes Jahr der Unternehmensgründung. Das Datum einer Patentanmeldung, eines Produktstarts oder eines Registereintrags braucht eine ausdrückliche Bestätigung als Gründungsdatum. |

Halte pro belegter Angabe die Quellen-URL und die relevante Aussage fest. Fehlende Werte bleiben unbekannt. E-Mail-Adressen und fehlende Datumsteile werden nicht aus Namen, Domains oder Datumsformaten abgeleitet.

Der aktuelle Einstiegspunkt ist `sourcing.engine.search(criteria: SearchCriteria) -> list[RawLead]`. `pipeline.discover` prüft Deutschlandbeleg und Branche, dedupliziert nach ID und setzt das Trefferlimit. Verwende über Quellen hinweg dieselbe ID, wenn die Unternehmensidentität anhand einer Registerkennung oder einer belegten offiziellen Domain eindeutig abgeglichen werden kann. Der echte Sourcing-Anbieter ist im aktuellen Stand ein Platzhalter.

`RawLead` enthält bereits Unternehmensname, Branche, Fundquelle und Sitzbeleg. `EnrichedLead` führt Website, Gründer:innen und `founded_on` als vollständiges Datum. E-Mail und Gründungsdaten mit Monat/Jahr ohne bekannten Tag brauchen eine Erweiterung des gemeinsamen Datenvertrags in [`models.py`](../models.py), die mit dem Team abgestimmt wird. Klärt dabei, wie bereits im Screening gefundene Angaben samt Belegen in die Kontextstufe gelangen. Die bestehenden Verträge verlangen, dass Folgestufen die Eingangsdaten erhalten.

## Quellen

| Quelle | Vorgehen und Machbarkeit |
| --- | --- |
| Patentdatenbanken | Recherchiere nach Technologiebegriffen oder Patentklassen in DEPATISnet. Prüfe den Anmelder oder Inhaber und ordne das Patent bei eindeutiger Zuordnung einem Unternehmen zu. Erfinderrolle und Gründerrolle brauchen eigene Belege. Der automatisierte Abruf über DPMAconnectPlus setzt eine Anbindung mit Anschlussgebühr voraus. [DPMA-Recherche](https://www.dpma.de/en/ip-search/databases/depatisnet) · [DPMAconnectPlus](https://www.dpma.de/recherchieren/datenabgabe/dpmaconnectplus) |
| Unternehmensregister | Nutze branchenbezogene Keywords in den dafür verfügbaren Suchbereichen und prüfe den Unternehmenssitz im konkreten Treffer. Die Suchbereiche decken unterschiedliche Daten ab. Bestimmte Dokumentabrufe erfordern eine Sicherheitsabfrage. Für solche Abrufe kommen im MVP eine manuelle Prüfung oder ein freigegebener Datenzugang infrage. [Suchhilfe des Unternehmensregisters](https://www.unternehmensregister.de/de/so-gehts/suche?dest=ureg&language=de) |
| Studentische Organisationen mit Gründungsbezug | Prüfe veröffentlichte Startup- und Alumni-Listen oder Beiträge zu Pitch-Veranstaltungen, etwa bei START Munich. Verifiziere bei jedem Hinweis separat, ob das Unternehmen bereits gegründet ist und seinen Sitz in Deutschland hat. [START Munich](https://www.startmunich.de/) |
| Forschungsinstitute | Nutze veröffentlichte Ausgründungslisten und Technologietransfer-Meldungen, etwa bei Fraunhofer ISE. Ein Institut kann mehrere Ausgründungen nennen, deren Sitz und Branche jeweils einzeln geprüft werden. [Fraunhofer ISE – Ausgründungen](https://www.ise.fraunhofer.de/de/ueber-uns/spin-offs.html) |
| GitHub | Suche bei passender Branche nach aktiven öffentlichen Repositories und Profilen. Relevante Beiträge oder Releases sind Hinweise auf ein Projekt. Für einen Treffer braucht es eine belegbare Verbindung zwischen dem Projekt und einem deutschen Unternehmen. [GitHub REST API – Events](https://docs.github.com/en/rest/activity/events) |
| Show HN | Rufe aktuelle Beiträge über die offizielle Hacker-News-API (`/v0/showstories`) ab. Folge dem Produktlink und prüfe Unternehmen, Sitz und Branche. Der Feed liefert bis zu 200 aktuelle Beiträge. [Offizielle Hacker-News-API](https://github.com/HackerNews/API#ask-show-and-job-stories) |

## Rolle von Qwen

Python ruft die Quellen über dokumentierte Schnittstellen oder verfügbare öffentliche Seiten ab und übergibt relevante Ausschnitte an das lokal laufende Qwen-Modell. Qwen kann Suchbegriffe vorschlagen, Angaben aus den Texten extrahieren und sie einer Kategorie aus `Industry` zuordnen. Python validiert die strukturierte Ausgabe und prüft Pflichtfelder, Sitzbeleg und Dubletten vor der Übergabe. Der Abruf aktueller Onlinequellen braucht Netzwerkzugang, während die Verarbeitung durch Qwen lokal läuft.

Beginne mit einem durchgängigen Lauf von einer Quelle über Qwen bis zu `RawLead`. Prüfe, dass ein passendes deutsches Unternehmen mit Sitzbeleg einmal erscheint, Treffer mit ausländischem oder unklarem Sitz aus der Liste fallen und fehlende optionale Angaben unbekannt bleiben. Ergänze weitere Quellen über dieselbe Schnittstelle.

## Machbarkeit bei jeder Aufgabe offen benennen

Wenn eine Idee technisch nicht umsetzbar ist oder mit den verfügbaren Daten, Zugängen oder der Hackathon-Zeit nicht zuverlässig funktioniert, sage das direkt. Nenne den konkreten Grund und zeige eine umsetzbare Alternative. Wenn eine Voraussetzung noch geprüft werden muss, kennzeichne die Idee als offen. Weise bei unvollständiger Quellenabdeckung darauf hin, welche Treffer der aktuelle Stand zuverlässig liefern kann.
