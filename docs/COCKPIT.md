# Investment-Cockpit: Daten und Integrationen

Der Ablauf beginnt bei der Branche. Die bestehende Pipeline liefert den Analyselauf
automatisch an das Dashboard. Es gibt keine Upload-Stufe. Der produktive Start ist
`python -m streamlit run cockpit.py`; `app.py` bleibt als bisheriger Fallback erhalten.

## Was mit den vorhandenen Daten funktioniert

| Investmentfrage | Darstellung | Datengrundlage |
| --- | --- | --- |
| Welche Firmen zuerst prüfen? | Review Queue und Qualität/Confidence-Scatter | Vorhandene Scores; unbekannte Werte werden ausgelassen |
| Wie verteilt sich die Pipeline? | Phasen als horizontale Balken | Tatsächliche Firmenanzahl je Stage, inklusive unbekannter Stage |
| Warum Firma, Team, Markt und jetzt? | Kompakter Investment Brief | Gelieferte Hypothese, Gründerangaben und Quellen; Lücken bleiben sichtbar |
| Was kann schiefgehen? | Separater Risikoindikator und Hauptrisiko | Risiko 100 bedeutet hohes Risiko; keine Vermischung mit positiven Scores |
| Wie gut ist die Beleglage? | Evidence-Chart und Source Explorer | Anzahl Records mit/ohne URL, keine behauptete unabhängige Bestätigung |
| Was mache ich als Nächstes? | Plan next step und Activities | Owner, Termin, Kontaktstatus, Open/Done, lokale Historie |
| Wie kontaktiere ich die Firma? | Open email draft oder Website-Fallback | Gültige gelieferte E-Mail-Adresse; Versand im eigenen Mailprogramm |
| Wie sähe ein Einstieg aus? | Ownership-/Exit-Szenario | Explizite Analystenannahmen, keine behauptete Unternehmensbewertung |

## Was noch Daten oder Integrationen braucht

| Bereich | Aktuelle Grenze | Nächster Integrationsschritt |
| --- | --- | --- |
| Echtes Sourcing | `sourcing.engine.search` ist nicht implementiert. Default ist Demo. | Einen Provider anschließen, der belegte `RawLead`-Datensätze liefert. |
| Live-Scoring | Evaluation übersetzt den Context-Vertrag in das vorhandene Scoring. Vollständige Scoring-Evidence, Teilwerte und Ausschlüsse werden unter `evaluation_v2` erhalten. Nicht jedes Kriterium kann bereits recherchiert werden. | Fehlende Kriterien mit belegtem Research versorgen; neutrale Defaults bleiben als unbewertet erkennbar. |
| Marktgrößen und Wachstum | Keine vergleichbaren TAM/SAM/SOM- oder historischen Reihen im Standardoutput. | Quellenanbieter/Research-Schritt plus strukturierter Vertrag mit Geografie, Definition, Jahr, Einheit und Methodik. |
| Wettbewerber und Transaktionen | Einzelne Namen/Texte statt vergleichbarer Finanz- und Wettbewerbsdaten. | Öffentliche Unternehmensquellen oder lizenzierter Datenanbieter; Begriffe und Währungen harmonisieren. |
| Retention, ARR, Unit Economics | Fehlende interne Geschäftszahlen. | Gründerunterlagen oder freigegebene Finanzdaten; Quellen und Perioden dokumentieren. |
| Automatische E-Mails und Antworten | `mailto:` öffnet nur den Entwurf. Kein Versand- oder Antwortnachweis. | Gmail-/Microsoft-365-Anbindung mit Freigabe, Message-ID und Status-Synchronisierung. |
| Monitoring über die Zeit | Ein Analyselauf je Sitzung und eine aktuelle Folgeaufgabe pro Firma. | Persistierte Läufe, Refresh-Jobs, Datenhistorie, mehrere Tasks und Benachrichtigungen. |
| Teamnutzung | Freitext-Owner, lokale SQLite-Datei, keine Nutzerverwaltung. | Authentifizierung, Rollen und gemeinsam betriebene Datenbank. |

Die optionalen Research-Strukturen in `cockpit_data.py` sind für Legacy/v2-Records
vorbereitet. Der strenge native Pydantic-Vertrag enthält noch nicht alle Markt- und
Transaktionsfelder. Für echte automatische Marktcharts müssen sowohl Enrichment
als auch der native Vertrag diese Felder liefern. Ein Bild oder eine KI kann diese
fehlende Datenbasis nicht ersetzen.

## Ist eine lokale KI nötig?

Für Dashboard, Filter, Charts, Fund-Fit-Heuristik, Szenariorechnung und Aufgaben
ist keine zusätzliche KI nötig. `context/ollama.py` enthält bereits einen optionalen
lokalen Extraktor. Mit `FOUNDERRADAR_MODE=live` und
`FOUNDERRADAR_OLLAMA_MODEL=<installiertes Modell>` wird er an den Context-Schritt
gebunden. Ollama muss separat auf `127.0.0.1:11434` laufen; ein Modell wird nicht
automatisch heruntergeladen.

Der Extraktor übernimmt nur wörtlich belegte Zitate aus gelieferten Quellenausschnitten.
Er findet nicht selbstständig neue Firmen, Marktstudien oder proprietäre Umsatzzahlen.
Eine spätere KI-Zusammenfassung kann Research strukturieren und Entwürfe formulieren,
braucht aber weiterhin Quellen, Faktenprüfung und einen expliziten Datenvertrag.

## Review und Prüfung

Das Layout wurde in mehreren Runden gegen fünf Fragen geprüft: Investmentcockpit,
schnelle Erstentscheidung, nächste Schritte, Tracking und Kontaktaufnahme.
Agent-Reviews prüfen Informationsarchitektur und Grenzfälle; die visuelle Prüfung
erfolgt zusätzlich im lokalen Browser. Die Referenzdaten bleiben als Regressionstests
erhalten. UI-Tests führen Branchenauswahl, Pipeline, Navigation, Aufgaben, Entscheidungen,
Neustart-Persistenz und leere Filteransichten aus. Store-Tests prüfen Migration,
Demo/Live-Trennung und Rollback bei einem fehlschlagenden History-Write.
