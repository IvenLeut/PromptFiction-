# Runde 1 – Coder B (`scorer`): Team-Zusammensetzung im Scoring, n2, n1

Stand 21.11.2026. Nur `scoring/`, `evaluation/engine.py` und Scoring-Tests. Gewichte unverändert (0,40/0,25/0,35),
`models.py` unverändert, in `scoring_config.yaml` nur ergänzt. Nichts committet.

## Profilformat (mit Coder A abgestimmt)

`founder_profiles[].role = "<Rolle> (<Herkunft>)"`, mehrere Quellen mit „; “ verbunden, Herkunft ∈ Impressum, LinkedIn,
Presse, Website. „Teammitglied (…)“ ist kein Gründer. `background` ∈ tech, business, beides oder None. „Alleingründer
(…)“ nur, wenn eine Quelle das ausdrücklich sagt.

## Änderungen

1. **`to_dossier`**: Jede Person trägt `herkunft` (erste), `herkuenfte` (alle) und `gruender`, geparst aus den
   Rollen-Suffixen. Profile ohne Suffix gelten als „kontext“, Schritt-1-Gründer als „sourcing“, die Impressum-GF als
   „impressum“. Abgleich über den Namen, kein Duplikat. Neu sind außerdem `in_databases_quelle` (nur positive Fundstelle)
   und `in_databases_konflikt` (n2).
2. **`k_komplementaer`**:
   - Für n zählen nur Gründer und Geschäftsführung. Teammitglieder zählen nur für den Mix.
   - Mix belegt → 1,0. Die Aussage nennt Namen, Rollen und die Person mit Business-Profil, deren URL der Beleg ist.
   - „ohne Business“ (0,5) gibt es nur, wenn **alle** Gründer einen belegten Tech-Hintergrund haben. Dann kommt der
     offene Punkt „Business-Profil im Team nicht belegt – prüfen“.
   - Fehlende Hintergründe → Mix unbekannt (0,6).
   - „solo“ (0,2) nur bei „Alleingründer“ oder in einem handgepflegten Dossier ohne Herkunft. Eine einzelne gefundene
     Person (Impressum, LinkedIn, Presse, OpenAlex) fällt auf die Förderdaten zurück: **kein Abzug mehr aus fehlenden
     Daten**. hochquant: 51,3 → 54,3.
   - `name_gruender` enthält keine Teammitglieder mehr.
3. **Hypothese**: Ein belegter Business-Co-Founder erscheint über `komplementaer` = 1,0 als Stärke („… mit Technik und
   Business: …; Business-Profil: …“).
4. **n2 (HydroPURE)**:
   - Ein positiver Datenbankbefund hat als Fundstelle immer eine Profil-URL (Dealroom & Co. oder ein archivierter
     Snapshot), nie eine Such-URL.
   - Findet nur Wayback einen Slug und die Datenbanksuche nichts, ist das ein Konflikt. Dann steht in `why_now`
     „Crunchbase-/Dealroom-Slug im Webarchiv, Datenbanksuche ohne Profil – Namensvetter prüfen“, dazu ein offener Punkt.
     Der Eintrag zählt dann weder zur Bestätigung eines Gründungsjahrs noch für den Altersausschluss.
5. **n1 (Website-VP)**:
   - Verworfen werden kurze, wiederholte Menüzeilen, Überschriften im Title Case ohne Satzzeichen, zusammengeklebte
     Menüeinträge sowie „explore/discover/looking for/LinkedIn/Co-Founder“-Sätze.
   - Bevorzugt wird eine Aussage über das eigene Produkt („we develop …“, „our sensor …“, Regex
     `texte.website_eigenaussage`).
   - Ein zweiter Satz wird nur angehängt, wenn er ein Satz ist.
   - Ergebnis:
     - iNSyT: „Our real-time, non-invasive technology brings unseen processes to light …“
     - SpinMagIC: „Our cutting-edge quantum sensor enables precise, real-time monitoring of free radicals …“
     - Metubiq: „Gain early access to our latest measurement technology …“, nicht mehr „explore our core technology“.
       Das ist noch Werbesprache, für den halben Aufwand aber ausreichend.
6. Grammatik: „1 belegter Wettbewerber“.

## Messung (Stichtag 2026-11-21, `AGENT_TEAM/reports/scratch/scorer/loop1/messung.py`)

| | gate2 vorher | gate2 nachher | Pilot (10 Leads, Coder A) |
|---|---|---|---|
| K2 Profil-Mix belegt, ohne Proxy | 0/52 | 0/52 | **1/10** (Ymolution: beide GF tech → „ohne Business“, offener Punkt) |
| K4 Spearman gesamt (30 Agent-Labels, unbestätigt, zirkulär zur Websuche) | 0,42 | **0,42** | 0,62 (n = 6) |
| Spearman ohne Website | 0,26 (n = 20) | 0,26 | – (n = 3) |
| Spearman mit Website | 0,32 (n = 10) | 0,32 | – |
| Ymolution / SECARA | Rang 5 / 14 | 5 / 14 | 3 / 7 |
| Leads mit Person | 17/52 | 17/52 | 6/10 |

- **gate2 unverändert:** Erwartet, denn die gate2-Dossiers haben noch keine Team-Daten (Herkunft nur Impressum, kein
  `background`). Die Wirkung kommt erst mit dem Volllauf des Coders A. Dieser Volllauf lag zum Messzeitpunkt nicht vor,
  nur die Pilot-Dossiers in `scratch/loop1/`.
- **Pilot:** 5 Leads mit ≥ 2 Gründern bleiben „Mix unbekannt“, weil bei je mindestens einer Person der Hintergrund
  fehlt (z. B. SECARA: Nagel ohne Hintergrund). K2 ≥ 10/52 hängt also an der `background`-Abdeckung aus context
  (Rollen- und Ausbildungswörter), nicht an der Scoring-Regel.
- **K4:** „nicht schlechter“ ist erfüllt. Spearman ohne Website (0,26) lag schon vorher unter 0,40; diese Runde ändert
  daran nichts.
- **Technik:**
  - Suite **831 passed**.
  - gate2-, Pilot- und 733er-Lauf sind beim zweiten Lauf byte-identisch.
  - Schema 0 Fehler, 0 Evidence ohne URL und ohne Kennzeichnung.
  - Beispiele neu erzeugt: hochquant ohne Solo-Abzug, sonst nur Texte.

## Tests (neu in `tests/test_scoring_differentiation.py`)

- `test_linkedin_founder_and_imprint_director_merge_without_duplicate`
- `test_business_cofounder_is_a_strength` (CEO business + CTO tech → 1,0, Beleg-URL der Business-Person, Hypothese)
- `test_without_business_only_when_all_founders_are_proven_tech` (alle tech → 0,5 + offener Punkt; CEO ohne Hintergrund → 0,6, kein Punkt)
- `test_team_members_count_for_mix_not_for_n` (Teammitglied liefert den Mix, zählt nicht für n und steht nicht in `name_gruender`)
- `test_single_person_is_solo_only_when_a_source_says_so`
- `test_database_hit_needs_a_profile_url_and_conflicts_are_flagged` (n2, HydroPURE-Fall)
- `test_website_vp_skips_menus_and_calls_to_action` (n1: iNSyT, Metubiq, SpinMagIC)

## Offen

- K2 auf den 52 Leads messen, sobald der Volllauf des Coders A vorliegt: `messung.py` auf dessen scores.json.
- Ob ein OpenAlex-Profil (≥ 5 Arbeiten) als „belegter Tech-Hintergrund“ für „ohne Business“ reicht, entscheidet der
  Sinn-Check. Bei Ymolution ergibt das 0,5 statt 0,6 (−0,8 Gesamtpunkte) und einen Prüfpunkt. Der CEO Reder hat
  vermutlich trotzdem kaufmännische Verantwortung, nur ist sie nicht belegt.
- Die Website-VP ist teils Werbesprache. Eine Umformulierung durch ein Modell bleibt eine Team-Entscheidung.

## Korrektur nach Prüfbericht Runde 1 (MAJOR 1)

Ein `tech`-Hintergrund nur aus dem OpenAlex-Fallback (context-Evidence „<Name>: background tech aus OpenAlex“) setzt in
`to_dossier` `hintergrund_quelle = openalex` und begründet kein „ohne Business“ mehr. Der Mix bleibt dann unbekannt (0,6).
„ohne Business“ verlangt jetzt einen ausdrücklichen Tech-Hintergrund aus Rolle oder Ausbildung bei allen Gründern. Ein
OpenAlex-tech zusammen mit einem ausdrücklichen Business-Co-Founder ergibt weiterhin „Mix belegt“.

Volllauf `scratch/loop1/full_dossiers.json` (52 Leads, Stichtag 2026-11-21), komplementaer-Punkte / Gesamt / Rang:

| Lead | vorher | nachher |
|---|---|---|
| iNSyT | 50 / 66,3 / 3 | 60 / 67,1 / 3 |
| Ymolution | 50 / 63,9 / 5 | 60 / 64,7 / 5 |
| Metubiq | 50 / 62,1 / 12 | 60 / 62,9 / 8 |
| BEHtec | 50 / 58,5 / 24 | 60 / 59,3 / 20 |
| LayerPerformance | 50 / 58,3 / 26 | 60 / 59,1 / 21 |

- **K2 sinkt von 5/52 auf 0/52.** Alle fünf Treffer beruhten auf dem OpenAlex-Fallback; im Volllauf ist kein Business-
  und kein ausdrücklicher Tech-Hintergrund aller Gründer belegt.
- K4 ist unverändert: Spearman 0,40 gesamt, 0,21 ohne Website, 0,32 mit Website.
- Test `test_openalex_fallback_tech_is_no_proof_of_missing_business`; Suite 833 passed.
- Volllauf und 733er-Lauf sind deterministisch, Schema 0 Fehler, Beispiele neu erzeugt.
