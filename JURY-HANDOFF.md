# FounderRadar an die Jury übergeben

Die Jury erhält **ein entpackbares Windows-ZIP mit dem befristeten Zugang zur Projekt-KI**. Im ZIP liegen das Cockpit, der öffentliche Referenzlauf, die Rechenregeln und Python für Windows x64/ARM64. Die Paketinstallation beim Erststart und die externe Projekt-KI benötigen Internet. Eigene Entscheidungen und Analyseverläufe speichert jede Kopie lokal.

## Vor dem Versand

1. Betreibe den FounderRadar-KI-Relay auf eurem Server, hinter einer erreichbaren HTTPS-Adresse. Der Relay bietet `GET /healthz` und `POST /v1/founderradar/insights` an. Die HTTPS-Terminierung liegt beim Hosting. Der Relay verwendet die OpenAI Responses API.
2. Erzeuge mit dem unkonfigurierten Release-ZIP einen befristeten Jury-Zugang. Beispiel im Repo mit aktivierter Python-Umgebung:

   ```powershell
   python -m mvp.issue_jury_access FounderRadar-Jury.zip https://demo.eure-domain.de --output FounderRadar-Jury-Versand.zip --relay-env ai-relay.env --hours 72 --budget 80
   ```

3. Hinterlege auf dem **Relay** die drei Werte aus der erzeugten `ai-relay.env` als Umgebungsvariablen. Lege `FOUNDERRADAR_PROJECT_OPENAI_KEY` separat als Server-Secret mit dem dedizierten Projekt-Key an. `FOUNDERRADAR_PROJECT_MODEL` bestimmt das Modell, standardmäßig `gpt-5-mini`. Codiere den Provider-Key weder in das Jury-ZIP noch in eine Client-Konfiguration. Den Serverzustand für das Abrufkontingent persistent unter `FOUNDERRADAR_RELAY_DB` speichern.
4. Starte die Anwendung auf eurem Host mit dem beiliegenden `Dockerfile.relay` oder `python -m mvp.ai_relay` nach Installation der Anforderungen. Der Container hört intern auf Port 8077. Rufe über die öffentliche Adresse `/healthz` ab und führe aus einer frisch entpackten Jury-Kopie eine echte KI-Auswertung durch.
5. Schicke der Jury **FounderRadar-Jury-Versand.zip**. Die erzeugte Datei `ai-relay.env` gehört zur Servereinrichtung. Der Jury-Zugang ist ein gemeinsamer, zeitlich und mengenmäßig begrenzter Relay-Zugang. Zusammen mit dem ZIP kann er innerhalb dieser Grenzen genutzt werden. Nach dem Pitch den Token serverseitig wechseln.

Das Projekt rechnet mit dem Key, der auf dem Relay liegt. Abrechnungs- oder Tracking-Zuordnungen bei OpenAI folgen diesem Projekt. Eine zusätzliche Tracking-ID eines anderen Dienstes benötigt dessen Schnittstellenbeschreibung. Source URLs und kurze öffentliche Belege werden an die Projekt-KI übergeben. Kontaktentwürfe, Notizen und gespeicherte Aufgaben gehören nicht zum Eingabesatz.

## Ablauf in der Demo

1. ZIP vollständig entpacken und `Start-FounderRadar.cmd` doppelklicken. Der Referenzlauf ist sofort sichtbar. Der erste Start auf einem neuen Rechner richtet die Laufzeit ein. Vor dem Pitch die Installation einmal auf dem Präsentationsrechner starten.
2. **Score jetzt berechnen** klicken. Der Rechner bewertet die sichtbaren Belege erneut. Stichtag, Lauf-ID und Ergebnis aktualisieren sich. Diese Berechnung funktioniert nach der Einrichtung offline.
3. **Live-Recherche starten** prüft zusätzlich Webseiten, Projektspuren und neue LEI-Firmen. Der ältere Stand bleibt währenddessen sichtbar und bleibt bei Fehlern oder Abbruch erhalten.
4. In der **Longlist** eine Karte öffnen und dort **KI-Auswertung erstellen** oder **aktualisieren** klicken. Kurzprofil, zwei Stärken, zwei Prüfrisiken, Markt, Investmenthypothese, Fazit und Teamkarten erscheinen mit Beleglinks. Das Modell bearbeitet den Score nicht.
5. Bei einer Störung der KI funktionieren Screening und Export weiter. Ein lokal bereits gespeicherter KI-Stand bleibt lesbar und zeigt sein Datum und den Quellenstand an.
6. Die Longlist als CSV oder den Deep Dive als HTML sichern. Details zur Methode und ein Export des Analyselaufs stehen unter **Demo und Daten**.

## Freigabecheck

- [ ] HTTPS-Relay erreichbar und Zugriff vom Rechner außerhalb des eigenen Netzes geprüft
- [ ] Echte OpenAI-Auswertung aus dem Versand-ZIP erfolgreich
- [ ] Start, Score-Neuberechnung, Longlist und Deep-Dive-Export einmal auf einem frischen Windows-Rechner geprüft
- [ ] Kontingent und Ablaufdatum reichen bis nach dem Pitch
