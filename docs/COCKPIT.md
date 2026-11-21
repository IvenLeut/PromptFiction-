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
| Welche operative Substanz gibt es? | Umsatz, Kundenzahl, Teamgröße und Kapital auf dem Firmenbrief; Details in Traction | Gelieferte flache Kennzahlen und periodisierte Recherchewerte; Umsatz ist nicht automatisch ARR |
| Was wurde zum Produkt und Team recherchiert? | Quellenverknüpfte Produkt-, Gründer- und Firmenprofile | Vollständige strukturierte Claims statt nur Namen und Kurzbeschreibung |
| Wie ist der Markt einzuschätzen? | Marktmodell, historische Reihen, Wachstumstreiber, Wettbewerber und Vergleichsfinanzierungen | Vorhandenes Marktdossier mit Einheiten, Bezugsjahren, Methodik und Quellen |

## Was noch Daten oder Integrationen braucht

| Bereich | Aktuelle Grenze | Nächster Integrationsschritt |
| --- | --- | --- |
| Echtes Sourcing | Open-Data-Adapter implementiert; Datenabdeckung ist unvollständig. Default ist Demo. | Collector ausführen und `FOUNDERRADAR_MODE=live` setzen. Siehe [Discovery](OPEN_DATA_DISCOVERY.md). |
| Live-Scoring | Evaluation übersetzt den Context-Vertrag in das vorhandene Scoring. Vollständige Scoring-Evidence, Teilwerte und Ausschlüsse werden unter `evaluation_v2` erhalten. Nicht jedes Kriterium kann bereits recherchiert werden. | Fehlende Kriterien mit belegtem Research versorgen; neutrale Defaults bleiben als unbewertet erkennbar. |
| Marktgrößen und Wachstum | Vollständiger Vertrag und Renderer vorhanden. Im Demo-Bestand hat nur industrial-16 ein quantitatives Marktdossier. | Weitere Firmen mit gezielter Marktrecherche, Quellen oder validierten Market-Inputs versorgen. |
| Wettbewerber und Transaktionen | Strukturierte Vergleiche vorhanden; drei Wettbewerber und eine Vergleichsfinanzierung im Industrial-Dossier. Meist fehlen Bewertungs- und Ergebniskennzahlen. | Weitere öffentliche Quellen oder lizenzierte Daten; Finanzierung, Bewertung und Enterprise Value getrennt halten. |
| Retention, ARR, Unit Economics | Fehlende interne Geschäftszahlen. | Gründerunterlagen oder freigegebene Finanzdaten; Quellen und Perioden dokumentieren. |
| Automatische E-Mails und Antworten | `mailto:` öffnet nur den Entwurf. Kein Versand- oder Antwortnachweis. | Gmail-/Microsoft-365-Anbindung mit Freigabe, Message-ID und Status-Synchronisierung. |
| Monitoring über die Zeit | Ein Analyselauf je Sitzung und eine aktuelle Folgeaufgabe pro Firma. | Persistierte Läufe, Refresh-Jobs, Datenhistorie, mehrere Tasks und Benachrichtigungen. |
| Teamnutzung | Freitext-Owner, lokale SQLite-Datei, keine Nutzerverwaltung. | Authentifizierung, Rollen und gemeinsam betriebene Datenbank. |

`research_models.py` enthält den nativen Pydantic-Vertrag. `cockpit_context.py`
erhält die verschachtelten Claims, verknüpft sämtliche Evidence-IDs und ergänzt
fehlende flache Anzeigefelder. `cockpit_research_v2.py` stellt diesen Vertrag dar.
Legacy-Records bleiben unterstützt und die Originaldaten unverändert exportierbar.

## Datenprüfung und behobene Fehler

- Der offene Merge enthielt vier Konflikte. Beide Modell-Feldmengen sind erhalten;
  `published_on` bleibt mit den neuen Evidence-Datumsfeldern kompatibel.
- Die frühere flache Übernahme von `context_v2` überschrieb Gründernamen mit
  Claim-Objekten und ließ Produkt-, Traction- und Finanzierungsdetails aus.
  Jetzt bleiben Namen, Werte, Belegstatus und Quellen korrekt zugeordnet.
- Markt- und verschachtelte Gründer-/Finanzierungsquellen fehlten im Source Explorer.
  Die Erfassung erfolgt jetzt über alle Evidence-Records, ohne verschiedene Aussagen
  derselben URL zu einer Aussage zu verschmelzen.
- Operative Kennzahlen waren teilweise nur in Unterseiten oder gar nicht sichtbar.
  Vorhandene Werte stehen jetzt im Investmentbrief und in den passenden Untertabs.
- Widersprüchliche Gründungsdaten erzeugen keinen positiven Alters-Fit. Fehlende
  Zahlen bleiben unbekannt; vorhandene Nullwerte bleiben sichtbar.

Die fünf Branchen enthalten zusammen 150 Demo-Firmen. Ihr Datenumfang variiert.
Die aktuelle Bestandsprüfung findet 125 Teamgrößen, 120 Kundenzahlen, 100
Jahresumsätze und 110 Finanzierungsvolumina. Finanzierungsphase, Produktstatus und
Traction-Notizen liegen bei allen 150 Firmen vor. Die Werte werden gezeigt, soweit
sie für die gewählte Firma vorhanden sind; sie bleiben Demo-Angaben.
Das ausführliche Dossier `industrial-16` kombiniert öffentliche Referenzdaten mit
einem ausdrücklich fiktiven Unternehmen und transparenten Modellannahmen:
206.391 / 204.554 / 201.177 deutsche NACE-C-Unternehmen für 2021/2022/2023;
12.000 EUR angenommener Jahrespreis, 10 % erreichbarer Anteil, Kapazität 30 Kunden.
Daraus ergeben sich TAM 2.414.124.000, SAM 241.404.000 und SOM 360.000 EUR/Jahr.
Die Zeitreihe zeigt Unternehmensbestand, keine Umsätze. Die Zentio-Referenz von
1,4 Mio. EUR bezeichnet eine Pre-Seed-Finanzierung, keine Bewertung oder ein Multiple.
Quellenstatus stammt aus der Recherchepipeline und ist keine erneute Prüfung durch
das Dashboard. Die übrigen Firmen erhalten keine kopierten Marktwerte.

## Ist eine lokale KI nötig?

Für Dashboard, Filter, Charts, Fund-Fit-Heuristik, Szenariorechnung und Aufgaben
ist keine zusätzliche KI nötig. `context/ollama.py` enthält bereits einen optionalen
lokalen Extraktor. Mit `FOUNDERRADAR_MODE=live` und
`FOUNDERRADAR_CONTEXT_MODE=live` sowie `FOUNDERRADAR_OLLAMA_MODEL=<installiertes Modell>` wird er an den Context-Schritt
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

Prüfstand dieser Layout-Runde: Branchenauswahl im lokalen Browser gesichtet;
Dashboard- und Detailnavigation über Streamlit-AppTests geprüft. Die vollständige
visuelle Abnahme der Dashboard-Ansichten ist offen: Das Vorschaufenster wurde
minimiert und die UI-Steuerung meldete konkurrierende Benutzereingaben. Die
Agent-Reviews bestätigen die Informationsarchitektur, keine vollständige optische
Abnahme oder Prüfung auf allen Bildschirmgrößen.

Die kombinierte Discovery und der schnelle Betrieb mit gespeicherten Analyseläufen stehen in [COMBINED_DISCOVERY.md](COMBINED_DISCOVERY.md).
