# FounderRadar – Start- und Testanleitung

## 1. Starten

Das Abgabe-ZIP vollständig in einen Ordner entpacken oder den Abgabe-Branch klonen. Beide Varianten enthalten Code und denselben öffentlichen Referenzlauf.

| Aufgabe | Datei | Voraussetzung |
| --- | --- | --- |
| Ergebnisse ansehen | `Ergebnisse/ERGEBNISSE.html` | Browser |
| Cockpit öffnen und Scores berechnen | `Start-FounderRadar.cmd` | 64-Bit-Windows. Der Erststart richtet Python und die Pakete mit Internetzugang ein. |
| KI live vorführen | `Start-Live-KI.cmd` | Internet und euer OpenAI-Projektschlüssel. Den Schlüssel beim Start verdeckt eingeben und das Fenster offen lassen. |
| Aktuellen Stand als HTML und CSV exportieren | `Ergebnisse-aktualisieren.cmd` | Eingerichtetes Cockpit. Aktualisiert den entpackten Ordner `Ergebnisse`. |

Die normale Ansicht öffnet das Cockpit im lokalen Browser. Die KI-Demo ruft mit eurem Projektschlüssel die OpenAI API auf. Die Jury braucht für die Ergebnisansicht keinen Schlüssel.

## 2. Berechnung vor dem Pitch prüfen

1. Eine frische Kopie des Abgabe-ZIPs verwenden. Im Cockpit alle fünf Branchen ausgewählt lassen. In **Start & Übersicht** auf **Score jetzt berechnen** klicken. Der Klick verwendet den gespeicherten Referenzlauf und dessen Stichtag **21.11.2026**.
2. Die Übersicht zeigt beim mitgelieferten Stand **8 bewertbare Unternehmen** und **26 mit offenen Nachweisen**. In der Longlist **REFACTUM GmbH** öffnen. Der Screening-Score muss **69,0 von 100** sein. Im Bereich für Score und Quellen stehen die drei Teilwerte **85, 50 und 70**.
3. Ein Firmenprofil mit **Recherche offen** öffnen. Dort müssen die fehlenden Nachweise sichtbar sein. Der Score bleibt offen.
4. Dieselbe Berechnung erneut auslösen. Bei identischem Belegstand, Stichtag und Branchenfilter bleiben Score und Reihenfolge gleich.

| Kriterium | Gewicht | REFACTUM |
| --- | ---: | ---: |
| Produkt und Technologie | 40 % | 85 |
| Kunde und Nutzen | 35 % | 50 |
| Entwicklungsnachweis | 25 % | 70 |

`85 × 0,40 + 50 × 0,35 + 70 × 0,25 = 69,0`. Fehlende Kriterien erhalten keine Ersatzpunkte. Die Rangfolge verwendet die belegte Untergrenze des Scores. Datenabdeckung und offene Risiken stehen separat neben der Bewertung. Die Regeln liegen in [config/early_stage.v2.json](config/early_stage.v2.json).

### Dieselbe Score-Berechnung in PowerShell

Nach dem ersten Start im entpackten Projektordner ausführen. Dieser Test schreibt seinen Lauf in einen separaten temporären Ordner.

```powershell
$vorherigerDatenordner = $env:FOUNDERRADAR_MVP_DATA
$env:FOUNDERRADAR_MVP_DATA = Join-Path $env:TEMP ("founderradar-test-" + [guid]::NewGuid())
try {
    .\.venv\Scripts\python.exe -m mvp.engine --mode replay --as-of 2026-11-21
    $lauf = Get-Content (Join-Path $env:FOUNDERRADAR_MVP_DATA 'latest.json') -Raw | ConvertFrom-Json
    $lauf.counts | Select-Object ranked, research, web_requests
    $lauf.assessments | Where-Object { $_.dossier.name -eq 'REFACTUM GmbH' } | Select-Object score, queue
} finally {
    $env:FOUNDERRADAR_MVP_DATA = $vorherigerDatenordner
}
```

Erwartet sind `ranked = 8`, `research = 26`, `web_requests = 0` und `score = 69` für REFACTUM.

## 3. Live-KI und Export prüfen

1. `Start-Live-KI.cmd` starten und im REFACTUM-Profil **KI-Auswertung erstellen** oder **KI-Auswertung aktualisieren** wählen. Prüfen, ob ein neuer Zeitstempel, Modellname, Investmenthypothese, Stärken, Prüfrisiken und anklickbare Quellen erscheinen. Der deterministische Score bleibt bei derselben Eingabe gleich.
2. `Ergebnisse-aktualisieren.cmd` ausführen und den Browser-Bericht öffnen. Der Bericht übernimmt validierte KI-Auswertungen für denselben Belegstand. Das ursprüngliche ZIP bleibt eine Momentaufnahme. Zum Weitergeben neuer Ergebnisse den Ordner `Ergebnisse` separat zippen.
3. **Live-Recherche starten** nur zusätzlich testen, wenn neue Quellen geholt werden sollen. Sie nutzt öffentliche Register- und Webquellen und kann einige Minuten dauern.

Im mitgelieferten Bericht sind die bereits berechneten Recherche- und Screening-Ergebnisse enthalten. Der Live-KI-Test muss einmal mit dem Projekt-Key auf eurem Präsentationsrechner ausgeführt werden.
