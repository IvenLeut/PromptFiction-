"""Bewertungsalgorithmus: Lead-Dossier -> belegter Score-Datensatz.

Deterministisch und regelbasiert. Ein Fakt zählt nur, wenn er selbst eine Quellen-URL trägt
({"wert": ..., "quelle": "https://..."} bzw. "quelle" am Listeneintrag). Es gibt keine Ersatzquellen.
Ohne Beleg geht ein Kriterium neutral (50) ein und senkt die Confidence. Es wird nie geraten.
Läuft mit Python 3.9+, braucht nur PyYAML.

Ohne URL übernommen werden nur vier Metadaten des Sourcing-Schritts, weil sie dessen eigenes
Ergebnis sind: noise_class, match_confidence, in_databases und first_db_date.

Ablauf je Dossier (`_score`): Stammdaten -> Pflichtprüfung -> Kriterien je Achse (`_bewerte_dimensionen`)
-> Gesamtscore, Noise, Stage, Ausschluss (`_einordnung`) -> Texte (`_investmenthypothese`, `_why_now`).
Unbekannte Dossier-Schlüssel werden ignoriert.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import logging
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).with_name("scoring_config.yaml")
# Oberste Schlüssel, die der Scorer liest (adapter_* nur evaluation/engine.py). Eine eigene --config braucht alle.
CONFIG_SCHLUESSEL = ("version", "dim3_name", "gewichte", "neutral", "ausschluss_max_gesamt", "htgf_max_alter_monate",
                     "exist_max_laufzeit_monate", "exist_nachlauf_monate", "hinweis_max_vor_signal_monate",
                     "zu_spaet_wenn_in_databases", "zu_spaet_wenn_alter_hinweis_bestaetigt", "zu_spaet_wenn_alter_db_eintrag",
                     "confidence_ohne_pflichtfelder", "email_erlaubte_postfaecher",
                     "adapter_zu_spaet_ab_funding_eur", "noise_agentur_woerter", "noise_beratung_woerter",
                     "noise_agentur_min_treffer", "noise_agentur_kernwoerter", "noise_tech_woerter", "noise_titel_muster",
                     "katalog", "texte", "kriterien")
BRANCHEN = ("digital_tech", "industrial_deep_tech", "climate_tech", "life_sciences", "chemie_materialien")
STAGES = ("pre_gruendung", "in_gruendung", "pre_seed", "seed", "zu_spaet")
NOISE = ("vc_potenzial", "hobby", "agentur", "studi_projekt", "beratung", "bereits_finanziert")
DIMENSIONEN = ("team", "marktpotenzial", "risiko")
MAX_ZAHL = 1e13
BRANCHE_ALIAS = {
    "digital": "digital_tech", "digital tech": "digital_tech", "ai / software": "digital_tech", "fintech": "digital_tech",
    "industrial": "industrial_deep_tech", "industrial / deeptech": "industrial_deep_tech",
    "industrial/deep tech": "industrial_deep_tech", "industrial deep tech": "industrial_deep_tech", "deep tech": "industrial_deep_tech",
    "climate": "climate_tech", "climatetech": "climate_tech", "climate tech": "climate_tech",
    "life sciences": "life_sciences", "healthtech": "life_sciences",
    "chemie": "chemie_materialien", "chemie/material": "chemie_materialien", "chemie / material": "chemie_materialien",
    "chemie materialien": "chemie_materialien",
}
NAECHSTER_MEILENSTEIN = {
    "idee": "ein Funktionsnachweis", "paper": "ein Laborprototyp", "labor_prototyp": "ein Prototyp beim Anwender",
    "prototyp": "ein erster Pilot", "pilot": "der erste zahlende Kunde", "erste_kunden": "wiederholbarer Vertrieb",
}
KRITERIUM_LABEL = {
    "forscher_match": "Forscher-Match (Papers im Produktfeld)", "komplementaer": "komplementäres Gründerteam",
    "vollzeit": "Vollzeit-Signal", "vorerfahrung": "Vorerfahrung der Gründer", "marktvolumen": "Marktvolumen",
    "traktion": "Partner, Piloten oder Kunden", "skalierbarkeit": "Skalierbarkeit (Produkttyp)",
    "zielkunde": "Zielkunde und Geschäftsmodell", "wettbewerb": "Wettbewerber", "tech_reife": "Reifegrad der Technologie",
    "regulatorik": "Regulatorik", "ip": "Schutzrechte (IP)", "finanzierung": "bisherige Förderung",
    "datenlage": "Datenlage", "forschungsumfeld": "Forschungsumfeld (Institut)", "timing": "Timing (Förderphase)",
    "tech_tiefe": "Tech-Tiefe (Programm und Fachgebiet)",
}
BUNDESLAENDER = {"Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen", "Hamburg", "Hessen", "Mecklenburg-Vorpommern",
                 "Niedersachsen", "Nordrhein-Westfalen", "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt",
                 "Schleswig-Holstein", "Thüringen"}
INSTITUT_TEXT = {"aussenuniversitaer": "außeruniversitäre Forschungseinrichtung", "forschungsuni": "TU9-/Exzellenzuniversität",
                 "universitaet": "Universität", "hochschule": "Hochschule"}
SKALIERUNG_TEXT = {"software": "Software", "hardware": "Hardware", "hardware_software": "Hardware mit Software",
                   "wirkstoff": "Wirkstoff", "plattform": "Plattform"}
STAGE_TEXT = {"pre_gruendung": "Noch vor der Gründung", "in_gruendung": "Gerade in Gründung", "pre_seed": "Gegründet, Pre-Seed",
              "seed": "Seed-reif", "zu_spaet": "Zu spät für einen Erstkontakt"}


def load_config(path=None):
    cfg = yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    fehlt = [k for k in CONFIG_SCHLUESSEL if k not in (cfg if isinstance(cfg, dict) else {})]
    if fehlt:
        raise ValueError("Konfiguration unvollständig, es fehlt: %s" % ", ".join(fehlt))
    if abs(sum(cfg["gewichte"].values()) - 1) > 1e-9:
        raise ValueError("gewichte müssen zusammen 1.0 ergeben")
    for dim in DIMENSIONEN:
        if abs(sum(k["gewicht"] for k in cfg["kriterien"][dim].values()) - 1) > 1e-9:
            raise ValueError("Kriterien-Gewichte in '%s' müssen zusammen 1.0 ergeben" % dim)
    return cfg


# --- Eingaben säubern: alles Unbrauchbare wird zu None, nie zu einem Wert -------
def is_url(u):
    if not isinstance(u, str) or len(u) > 2083 or not re.fullmatch(r"https?://[^\s<>\"'`\\]+", u):
        return False
    try:
        host = urlparse(u).hostname or ""
    except ValueError:
        return False
    return re.fullmatch(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}", host.lower()) is not None


def clean(x, tiefe=0):
    """Dossier entschärfen: kaputte Zeichen und Steuerzeichen raus, nur str-Schlüssel, begrenzte Tiefe und Länge."""
    if isinstance(x, str):
        # Zeilenumbrüche bleiben (Website-Text ist zeilenweise); alle Textspalten werden später mit clip() eingeebnet
        return re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", x.encode("utf-8", "replace").decode("utf-8"))[:20000]
    if isinstance(x, (bool, int, float)) or x is None:
        return x
    if tiefe >= 8:
        return None
    if isinstance(x, dict):
        return {clean(k): clean(v, tiefe + 1) for k, v in list(x.items())[:500] if isinstance(k, str)}
    if isinstance(x, list):
        return [clean(v, tiefe + 1) for v in x[:1000]]
    return None


def text(x):
    return x.strip() if isinstance(x, str) and x.strip() else None


def num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    try:
        x = float(x)
    except OverflowError:
        return None
    return x if math.isfinite(x) and 0 <= x <= MAX_ZAHL else None


def dicts(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def nur_jahr(s):
    return isinstance(s, str) and re.fullmatch(r"\d{4}", s.strip()) is not None


def parse_date(s):
    if isinstance(s, dt.datetime):
        s = s.date()
    if isinstance(s, dt.date):
        return s if 1900 <= s.year <= 2100 else None
    if not isinstance(s, str):
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2})(?:[T ][0-9:.+Zz-]*)?)?)?", s)
    if m:
        teile = (m.group(1), m.group(2) or 1, m.group(3) or 1)
    else:
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
        if not m:
            return None
        teile = (m.group(3), m.group(2), m.group(1))
    try:
        d = dt.date(int(teile[0]), int(teile[1]), int(teile[2]))
    except ValueError:
        return None
    return d if 1900 <= d.year <= 2100 else None


def voll(s):
    """Nur taggenaue Daten (JJJJ-MM-TT oder TT.MM.JJJJ). Aus Jahr oder Monat allein wird kein Tag erfunden."""
    if isinstance(s, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ][0-9:.+Zz-]*)?|\d{1,2}\.\d{1,2}\.\d{4}", s.strip()):
        return None
    return parse_date(s)


def iso(x):
    d = voll(x)
    return d.isoformat() if d else None


def fact(x):
    """Feld -> (wert, url, datum). url ist None, wenn der Fakt keine eigene gültige Quelle trägt."""
    if isinstance(x, dict) and "wert" in x:
        q = x.get("quelle")
        return x["wert"], (q if is_url(q) else None), iso(x.get("datum"))
    return x, None, None


def months_between(a, b):
    return (b.year - a.year) * 12 + b.month - a.month - (1 if b.day < a.day else 0)


def stufe(stufen, n):
    for schwelle, wert in sorted(stufen, key=lambda s: -s[0]):
        if n >= schwelle:
            return wert
    return None


def r1(x):
    return float(Decimal(repr(round(x, 6))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def clip(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    cut = s[: n - 1]
    if " " in cut[n // 2:]:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


ABKUERZUNG = re.compile(r"(?:^|[\s(])(?:Dr|Prof|Dipl|Ing|Co|Fa|Nr|St|ca|bzw|inkl|etc|ggf|Mio|Mrd|ehem|\d{1,2}|[A-Za-zÄÖÜäöü])\.$")


def saetze(s):
    out = []
    for teil in re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9])", re.sub(r"\s+", " ", s or "").strip()):
        if out and ABKUERZUNG.search(out[-1]):
            out[-1] += " " + teil
        elif teil.strip():
            out.append(teil.strip())
    return out


def norm_branche(x):
    if not isinstance(x, str):
        return None
    key = x.strip().lower()
    if key in BRANCHEN:
        return key
    return BRANCHE_ALIAS.get(key) or BRANCHE_ALIAS.get(key.replace("_", " "))


def host(url):
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def domain(url):
    """Grobe registrierbare Domain (letzte zwei Labels), nur zum Zählen unabhängiger Quellen."""
    return ".".join(host(url).split(".")[-2:])


def wort_in(wort, s):
    return re.search(r"(?<!\w)%s(?!\w)" % re.escape(wort), s) is not None


VERNEINUNG = re.compile(r"(?i)(?<!\w)(kein\w*|nicht|ohne|no|not|non)(?!\w)")


def rolle_kurz(m):
    """Rolle ohne Herkunfts-Suffix: 'CTO & Co-Founder (LinkedIn)' -> 'CTO & Co-Founder'; mehrere Rollen mit ' / '."""
    teile = [re.sub(r"\s*\([^()]*\)\s*$", "", t.strip()) for t in str(m.get("rolle") or "").split(";")]
    teile = list(dict.fromkeys(t for t in teile if t))
    hg = {"tech": "Tech", "business": "Business", "beides": "Tech + Business"}.get(m.get("hintergrund"))
    return clip(" / ".join(teile) or "Rolle offen", 50) + (", %s" % hg if hg else "")


def wort_unverneint(wort, s):
    """Ganzes Wort, mindestens einmal ohne Verneinung in den drei Wörtern davor ("keine Agentur" zählt nicht)."""
    for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(wort), s):
        davor = re.findall(r"[\w-]+", s[max(0, m.start() - 60):m.start()])[-3:]
        if not any(VERNEINUNG.fullmatch(w) for w in davor):
            return True
    return False


def kurz_stelle(stelle):
    """Ausführende Stelle ohne Ort/Bundesland -> (institution, gruppe). gruppe = spezifischster Teil (Lehrstuhl, Institut ...)."""
    stelle = text(stelle)
    if not stelle:
        return None, None
    teile = [t.strip() for t in stelle.split(",")]
    if len(teile) >= 3 and teile[-1] in BUNDESLAENDER:
        teile = teile[:-2]
    stelle = ", ".join(teile)
    segmente = [x.strip() for x in re.split(r"\s+-\s+|(?<=\w)-(?=Fakult)", stelle) if x.strip()]
    if len(segmente) < 2 and len(teile) >= 2:  # "Universität Augsburg, Lehr- & Forschungseinheit …"
        return teile[0], ", ".join(teile[1:])
    if len(segmente) < 2:
        return stelle, None
    return segmente[0], segmente[-1]


def monate_bis(stichtag, ende):
    """Monate vom Stichtag bis `ende` (negativ: so viele Monate ist `ende` vorbei)."""
    return months_between(stichtag, ende) if ende >= stichtag else -months_between(ende, stichtag)


def eur(v):
    if v >= 1e9:
        return ("%.1f Mrd." % (v / 1e9)).replace(".", ",", 1)
    if v >= 1e6:
        return ("%.1f Mio." % (v / 1e6)).replace(".", ",", 1)
    return "{:,.0f}".format(v).replace(",", ".")


class Scorer:
    def __init__(self, dossier, cfg, stichtag):
        d = self.d = dossier if isinstance(dossier, dict) else {}
        self.cfg, self.stichtag = cfg, stichtag
        self.signals = []
        for s in dicts(d.get("signals")):
            datum = voll(s.get("datum"))
            if is_url(s.get("url")) and datum and datum <= stichtag:
                self.signals.append({"url": s["url"], "datum": datum, "typ": text(s.get("typ"))})
        self.signals.sort(key=lambda s: (s["datum"], s["url"]))
        self.team = []
        for m in self.dated_rows(d.get("team")):
            url = next((m[k] for k in ("quelle", "openalex", "openalex_url") if is_url(m.get(k))), None)
            if text(m.get("name")) and url:
                self.team.append(dict(m, name=text(m["name"]).replace(";", ","), _url=url))
        self.team.sort(key=lambda m: (m["name"], m["_url"]))
        roh, roh_url, _ = self.dated_fact(d.get("beschreibung_rohtext"))
        self.rohtext = text(roh) if roh_url else None
        self.branche = norm_branche(fact(d.get("branche") or d.get("htgf_bereich"))[0])
        self.foerderung, gesehen = [], set()
        def schluessel(f):
            return (str(parse_date(f.get("start")) or "9999"), f["quelle"], str(f.get("programm")), str(num(f.get("summe_eur"))), str(f.get("ende")))
        grants = (f for f in self.dated_rows(d.get("foerderung")) if is_url(f.get("quelle"))
                  and ((start := parse_date(f.get("start"))) is None or start <= stichtag))
        for f in sorted(grants, key=schluessel):
            if schluessel(f) not in gesehen:  # nur exakt gleiche Einträge zusammenfassen
                gesehen.add(schluessel(f))
                self.foerderung.append(f)
        self.markt = d.get("markt") if isinstance(d.get("markt"), dict) else {}

    def dated_fact(self, item):
        value, url, document_date = fact(item)
        if document_date and document_date > self.stichtag.isoformat():
            return None, None, None
        return value, url, document_date

    def dated_rows(self, items):
        return (item for item in dicts(items)
                if (document_date := voll(item.get("datum"))) is None or document_date <= self.stichtag)

    def enum(self, feld, erlaubt, quelle=None):
        v, url, datum = self.dated_fact(quelle if quelle is not None else self.d.get(feld))
        return (v, url, datum) if isinstance(v, str) and v in erlaubt and url else (None, None, None)

    # --- Förderkatalog: was Programm, Summe, Laufzeit und ausführende Stelle belegen -----------------
    def katalog(self):
        """Belegte Förderungen mit Katalog-Feldern, EXIST zuerst (Forschungstransfer vor Stipendium), dann jüngster Start."""
        if hasattr(self, "_katalog"):
            return self._katalog
        de, de_url, _ = fact(self.d.get("deutschland_beleg"))
        out = []
        for f in self.foerderung:
            programm = text(str(f.get("programm") or "")) or ""
            fkz = text(f.get("kennzeichen"))
            if not fkz:
                m = re.search(r"(?i)[?&]fkz=([0-9A-Za-z]+)", f["quelle"])
                fkz = m.group(1).upper() if m else None
            if re.search(r"(?i)exist.*forschungstransfer", programm) or (fkz or "").upper().startswith("03EF"):
                art = "ef"
            elif re.search(r"(?i)exist.*gr(ü|ue)nd(ungs|er)stipendium", programm) or (fkz or "").upper().startswith("03EG"):
                art = "eg"
            else:
                art = None
            stelle = text(f.get("ausfuehrende_stelle"))
            if not stelle and isinstance(de, str) and de_url == f["quelle"]:  # Deutschland-Beleg aus derselben Katalogseite
                m = re.search(r"Ausführende Stelle:?\s*(.+?)(?:, Ort |;|$)", de)
                stelle = text(m.group(1)) if m else None
            empf = text(f.get("empfaenger"))
            out.append(dict(url=f["quelle"], programm=programm, art=art, fkz=fkz, summe=num(f.get("summe_eur")),
                            start=parse_date(f.get("start")), ende=parse_date(f.get("ende")), empfaenger=empf, stelle=stelle,
                            thema=text(f.get("thema"))))
        rang = {"ef": 0, "eg": 1, None: 2}
        out.sort(key=lambda e: (rang[e["art"]], -(e["start"] or dt.date(1900, 1, 1)).toordinal(), e["url"]))
        self._katalog = [e for e in out if not e["start"] or e["start"] <= self.stichtag]
        return self._katalog

    def katalog_exist(self):
        return [e for e in self.katalog() if e["art"] and e["start"]]

    def proxy(self, wert):
        """Proxy-Wert: Abstand zum Neutralwert mit katalog.proxy_faktor skaliert."""
        n = self.cfg["neutral"] / 100.0
        return n + (wert - n) * self.cfg["katalog"]["proxy_faktor"]

    def ist_platzhalter(self):
        return bool(self.rohtext and re.fullmatch(self.cfg["katalog"]["platzhalter_muster"], self.rohtext))

    def fachtext(self):
        """Texte der Förderkatalog-Seite für Fachgebiets-Regeln: ausführende Stelle, Förderempfänger, Thema (Projekttitel).
        Selbstbeschreibungen (Website, Pressetext) zählen hier bewusst nicht: dort ist ein Schlagwort nur eine Behauptung,
        den Produkttyp daraus liefert der Kontext-Schritt als `produkt_typ`. -> (text in Kleinbuchstaben, url der ersten Quelle)."""
        teile, url = [], None
        for e in self.katalog():
            for t in (e["stelle"], e["empfaenger"], e["thema"]):
                if t:
                    teile.append(t)
                    url = url or e["url"]
        return " | ".join(teile).lower(), url

    def fach_treffer(self, schluessel, t):
        m = re.search(self.cfg["katalog"][schluessel], t, re.I)
        return m.group(0).strip() if m else None

    # --- Team (1 = stark) ---------------------------------------------------
    def k_forscher_match(self, k):
        best = None
        for m in self.team:
            p = m.get("papers_im_feld")
            if isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 100000 and (best is None or p > best[0]):
                best = (p, m["name"], m["_url"])
        if not best:
            return self.forscher_gesamt(k)
        return dict(wert=stufe(k["stufen"], best[0]), aussage="%s: %d Papers im Produktfeld" % (best[1], best[0]), url=best[2])

    def forscher_gesamt(self, k):
        """Proxy ohne Feldzuordnung: Publikationen insgesamt eines sicher zugeordneten OpenAlex-Profils (nie ein Malus)."""
        best = None
        for m in self.team:
            n, mc, oa = m.get("papers_gesamt"), num(m.get("match_confidence")), m.get("openalex")
            if (isinstance(n, int) and not isinstance(n, bool) and 0 < n <= 100000 and is_url(oa)
                    and mc is not None and mc >= k["gesamt_min_match"] and (best is None or n > best[0])):
                best = (n, m["name"], oa)
        if not best:
            return None
        return dict(wert=self.proxy(stufe(k["gesamt_stufen"], best[0])), proxy=True, url=best[2],
                    aussage="%s: %d Publikationen insgesamt (OpenAlex, Feldbezug offen)" % (best[1], best[0]))

    def gruender(self):
        """Gründer bzw. Geschäftsführung; Teammitglieder ohne Gründerrolle (`gruender: false`) zählen nicht für n."""
        return [m for m in self.team if m.get("gruender") is not False]

    def mix(self):
        """True = Technik und Business belegt (auch durch ein Teammitglied), False = alle Gründer mit belegtem
        Tech-Hintergrund und niemand mit Business-Profil, None = offen. Fehlende Angaben ergeben nie False."""
        v, url, _ = self.dated_fact(self.d.get("mix_tech_business"))
        if isinstance(v, bool) and url:
            return v
        h = [m.get("hintergrund") for m in self.team]
        if "beides" in h or ("tech" in h and "business" in h):
            return True
        gr = self.gruender()
        # "ohne Business" nur mit ausdrücklichem Tech-Hintergrund (Rolle/Ausbildung) aller Gründer; ein tech aus dem
        # OpenAlex-Fallback (Publikationen) sagt nichts über fehlende kaufmännische Verantwortung -> Mix bleibt offen
        if gr and all(m.get("hintergrund") == "tech" and m.get("hintergrund_quelle") != "openalex" for m in gr) and "business" not in h:
            return False
        return None

    def stipendium_personen(self):
        """Mindestzahl geförderter Personen aus Summe und Laufzeit eines Gründungsstipendiums (Obergrenzen laut Richtlinie)."""
        kat = self.cfg["katalog"]
        for e in self.katalog_exist():
            if e["art"] == "eg" and e["summe"] and e["ende"] and e["ende"] > e["start"]:
                monate = months_between(e["start"], e["ende"]) + 1
                n = math.ceil((e["summe"] - kat["stipendium_max_sach_coaching_eur"]) / (kat["stipendium_max_person_monat_eur"] * monate))
                return max(n, 1), monate, e
        return None

    def k_komplementaer(self, k):
        gr = self.gruender()
        einzeln = gr[0] if len(gr) == 1 else None
        solo_beleg = einzeln is not None and (not einzeln.get("herkunft") or re.search(
            r"(?i)allein\s*gr(ü|ue)nder|einzelgr(ü|ue)nder|solo[- ]?founder|sole founder", str(einzeln.get("rolle") or "")))
        # Eine einzelne gefundene Person (Impressum, LinkedIn, Presse …) ist kein Beleg für eine Solo-Gründung; "solo" nur
        # bei ausdrücklicher Angabe oder in einem handgepflegten Dossier ohne Herkunft. Sonst wie ohne Team (Förderdaten).
        if not gr or (einzeln is not None and not solo_beleg):
            wer = ("%s (%s), Teamgröße offen; " % (einzeln["name"], rolle_kurz(einzeln)) if einzeln is not None
                   else "%d Teammitglied(er) ohne Gründerrolle belegt; " % len(self.team) if self.team else "")
            sp = self.stipendium_personen()
            ef = next((e for e in self.katalog_exist() if e["art"] == "ef"), None)
            if (not sp or sp[0] < 2) and ef:  # Richtlinie: EXIST-Forschungstransfer fördert Forschungsteams
                return dict(wert=self.proxy(k["werte"]["forschungsteam"]), proxy=True, url=ef["url"], datum=iso(ef["start"].isoformat()),
                            aussage=wer + ("EXIST-Forschungstransfer fördert Forschungsteams" if wer else
                                           "EXIST-Forschungstransfer fördert Forschungsteams, Gründer noch nicht namentlich belegt"))
            if not sp or sp[0] < 2:
                return None
            n, monate, e = sp
            return dict(wert=k["werte"]["foerderung_ab_drei" if n >= 3 else "foerderung_ab_zwei"], url=e["url"], datum=iso(e["start"].isoformat()),
                        aussage=wer + "Stipendium %s EUR über %d Monate: nach EXIST-Obergrenzen mind. %d geförderte Personen" % (eur(e["summe"]), monate, n))
        n, mix = len(gr), self.mix()
        if n == 1:
            return dict(wert=k["werte"]["solo"], aussage="Ein Gründer belegt: %s" % einzeln["name"], url=einzeln["_url"])
        personen = ", ".join("%s (%s)" % (m["name"], rolle_kurz(m)) for m in gr[:4]) + (" …" if n > 4 else "")
        wer = "Personen in der Geschäftsführung" if all(m.get("herkunft") == "impressum" for m in gr) else "Gründer"
        if mix is True:
            biz = next((m for m in self.team if m.get("hintergrund") in ("business", "beides")), None)
            key, url = "mehrere_mit_mix", (biz or gr[0])["_url"]
            aussage = "%d %s mit Technik und Business: %s" % (n, wer, personen)
            if biz:
                aussage += "; Business-Profil: %s" % biz["name"]
        elif mix is False:
            key, url, aussage = "mehrere_ohne_business", gr[0]["_url"], "%d %s, alle mit Tech-Hintergrund, kein Business-Profil: %s" % (n, wer, personen)
        else:
            key, url, aussage = "mehrere_mix_unbekannt", gr[0]["_url"], "%d %s, Profil-Mix unbekannt: %s" % (n, wer, personen)
        return dict(wert=k["werte"][key], aussage=aussage, url=url)

    def exist(self):
        """Belegte EXIST-Förderungen, früheste zuerst."""
        muster = r"exist([\s_-]*(forschungstransfer|gr(ü|ue)ndungsstipendium|gr(ü|ue)nderstipendium))?([\s_-]*(i{1,2}|phase\s*\w+))?"
        out = []
        for f in self.foerderung:
            start, ende = parse_date(f.get("start")), parse_date(f.get("ende"))
            if not (re.fullmatch(muster, str(f.get("programm") or "").strip(), re.I) and start and start <= self.stichtag):
                continue
            # ohne Enddatum gilt die längste übliche Laufzeit; danach zählt die Förderung nicht mehr als aktuelles Signal
            vorbei = months_between(ende, self.stichtag) if ende else months_between(start, self.stichtag) - self.cfg["exist_max_laufzeit_monate"]
            if vorbei <= self.cfg["exist_nachlauf_monate"]:
                out.append(f)
        return out

    def k_vollzeit(self, k):
        ex = self.exist()
        if ex:
            return dict(wert=k["werte"]["ja"], aussage="Vollzeit-Signal: %s" % clip(str(ex[0]["programm"]), 60), url=ex[0]["quelle"], datum=iso(ex[0].get("start")))
        v, url, datum = self.dated_fact(self.d.get("vollzeit_signal"))
        if isinstance(v, bool) and url:
            return dict(wert=k["werte"]["ja" if v else "nein"],
                        aussage="Gründer arbeiten Vollzeit am Vorhaben" if v else "Kein Vollzeit-Engagement", url=url, datum=datum)
        return None

    def k_vorerfahrung(self, k):
        best = None
        for m in self.team:
            ve = m.get("vorerfahrung")
            for e in ([ve] if isinstance(ve, str) else ve if isinstance(ve, list) else []):
                if isinstance(e, str) and e in k["werte"] and (best is None or k["werte"][e] > best[0]):
                    best = (k["werte"][e], e, m["name"], m["_url"])
        if not best:
            return None
        wie = {"fruehere_gruendung": "hat bereits gegründet", "industrie": "hat Industrieerfahrung", "keine": "ohne Vorerfahrung"}[best[1]]
        return dict(wert=best[0], aussage="%s %s" % (best[2], wie), url=best[3])

    def k_forschungsumfeld(self, k):
        best = None
        for e in self.katalog():
            t = " ".join(x for x in (e["empfaenger"], e["stelle"]) if x)
            if not t:
                continue
            for kl in self.cfg["katalog"]["institut_klassen"]:
                klasse, ab, bis = kl["klasse"], parse_date(str(kl.get("ab") or "")), parse_date(str(kl.get("bis") or ""))
                if (ab and self.stichtag < ab) or (bis and self.stichtag > bis):
                    continue  # Klasse gilt zum Stichtag nicht (z. B. Exzellenz-Förderphase)
                if klasse in k["werte"] and re.search(kl["muster"], t, re.I):
                    if best is None or k["werte"][klasse] > best[0]:
                        best = (k["werte"][klasse], klasse, e)
                    break
        if not best:
            return None
        inst, gruppe = kurz_stelle(best[2]["stelle"] or best[2]["empfaenger"])
        wo = clip(inst or "", 90) + (", %s" % clip(gruppe, 90) if gruppe else "")
        return dict(wert=self.proxy(best[0]), proxy=True, url=best[2]["url"], datum=iso(best[2]["start"].isoformat()) if best[2]["start"] else None,
                    aussage="Forschungsumfeld: %s (%s)" % (wo, INSTITUT_TEXT[best[1]]))

    # --- Marktpotenzial (1 = groß) -------------------------------------------
    def k_marktvolumen(self, k):
        v, url, datum = self.dated_fact(self.markt.get("volumen_eur"))
        v = num(v)
        if v is None or not url:
            return None
        return dict(wert=stufe(k["stufen"], v), aussage="Marktvolumen %s EUR" % eur(v), url=url, datum=datum)

    def partner_geprueft(self, k):
        """Partner mit Quelle -> (stark, schwach). Verworfen: Fördergeber, Programme, generische Phrasen ("Global Partners"),
        Bruchstücke eines an "und/and" zerschnittenen Namens. Stark: Name mit Rechtsform oder bekannte Organisation;
        sonst schwach (zählt nur als Proxy)."""
        kat = self.cfg["katalog"]
        roh = [p for p in self.dated_rows(self.d.get("partner")) if isinstance(p.get("typ"), str) and p["typ"] in k["werte"]
               and is_url(p.get("quelle")) and text(p.get("name"))]
        # an "und/and" zerschnittene Namen wieder zusammensetzen: "<links> und <rechts>" steht so im Zitat
        voll, rechts_teile = {}, set()
        for p in roh:
            for o in roh:
                if o is not p:
                    m = re.search(re.escape(text(p["name"])) + r"(-?\s+(und|and|&)\s+)" + re.escape(text(o["name"])), str(p.get("zitat") or ""))
                    if m:
                        voll[id(p)] = text(p["name"]) + m.group(1) + text(o["name"])
                        rechts_teile.add(id(o))
        stark, schwach = [], []
        for p in roh:
            name = voll.get(id(p), text(p["name"]))
            if id(p) in rechts_teile or re.search(kat["partner_verwerfen"], name, re.I) or re.fullmatch(kat["partner_generisch"], name, re.I):
                continue
            # Organisation bestätigt: Rechtsform/Einrichtung im Namen oder direkt dahinter im Zitat ("… Materials (FCM) GmbH")
            nach = re.search(re.escape(name) + r"([^.;]{0,25})", str(p.get("zitat") or ""))
            bekannt = re.search(kat["partner_organisation"], name + " " + (nach.group(1) if nach else ""), re.I)
            (stark if bekannt else schwach).append(dict(p, name=name))
        return stark, schwach

    def k_traktion(self, k):
        stark, schwach = self.partner_geprueft(k)
        ok, proxy = (stark, False) if stark else (schwach, True)
        if not ok:
            return None
        best = max(ok, key=lambda p: (k["werte"][p["typ"]], text(p.get("name")) or "", p["quelle"]))
        wert = min(1.0, k["werte"][best["typ"]] + (k["bonus_ab_zwei"] if len(ok) >= 2 else 0))
        n = len(ok)
        aussage = "%d %s; stärkster: %s (%s)" % (n, "belegter Partner" if n == 1 else "belegte Partner",
                                                  clip(text(best.get("name")) or "ohne Namen", 60), best["typ"])
        return dict(wert=self.proxy(wert) if proxy else wert, proxy=proxy, url=best["quelle"], datum=iso(best.get("datum")),
                    aussage=aussage + (", Organisation nicht bestätigt" if proxy else ""))

    def fach_produkttyp(self):
        """Produkttyp-Proxy aus dem Fachgebiet: (typ, treffer, url) oder None."""
        t, url = self.fachtext()
        if not t or not url:
            return None
        wk, sw, hw = (self.fach_treffer(x, t) for x in ("fach_wirkstoff", "fach_software", "fach_hardware"))
        if wk:
            return "wirkstoff", wk, url
        if sw and hw:
            return "hardware_software", "%s, %s" % (hw, sw), url
        if sw:
            return "software", sw, url
        if hw:
            return "hardware", hw, url
        return None

    def k_skalierbarkeit(self, k):
        v, url, datum = self.enum("produkt_typ", k["werte"])
        if v:
            return dict(wert=k["werte"][v], aussage="Produkttyp: %s" % v, url=url, datum=datum)
        p = self.fach_produkttyp()
        if not p:
            return None
        return dict(wert=self.proxy(k["werte"][p[0]]), proxy=True, url=p[2],
                    aussage="Produkttyp vermutlich %s (Fachgebiet: %s)" % (SKALIERUNG_TEXT[p[0]], clip(p[1], 60)))

    def k_zielkunde(self, k):
        zk, u1, _ = self.dated_fact(self.markt.get("zielkunde"))
        zk = text(zk) if u1 else None
        mo, u2, _ = self.enum("modell", ("b2b", "b2c", "b2b2c"), self.markt.get("modell"))
        if not (zk or mo):
            return None
        return dict(wert=k["werte"]["beides" if zk and mo else "eines"],
                    aussage="Zielkunde: %s; Modell: %s" % (clip(zk, 80) if zk else "nicht belegt", mo or "nicht belegt"), url=u1 if zk else u2)

    def k_wettbewerb(self, k):
        ok = sorted((text(w.get("name")), w["quelle"]) for w in self.dated_rows(self.d.get("wettbewerber")) if text(w.get("name")) and is_url(w.get("quelle")))
        if not ok:
            return None
        key = "viele" if len(ok) >= k["viele_ab"] else "wenige"
        return dict(wert=k["werte"][key], aussage="%d %s: %s" % (len(ok), "belegter Wettbewerber" if len(ok) == 1 else "belegte Wettbewerber", clip(", ".join(n for n, _ in ok[:3]), 120)), url=ok[0][1])

    def foerderende(self):
        """(monate_bis_ende, eintrag) der EXIST-Förderung, die am spätesten endet; None ohne belegtes Enddatum."""
        mit_ende = [e for e in self.katalog_exist() if e["ende"]]
        if not mit_ende:
            return None
        e = max(mit_ende, key=lambda e: (e["ende"], e["url"]))
        return monate_bis(self.stichtag, e["ende"]), e

    def k_timing(self, k):
        fe = self.foerderende()
        if not fe:
            return None
        m, e = fe
        prog = clip(e["programm"] or "EXIST", 60)
        rf = self.rechtsform()
        if rf[0] and rf[0] != "keine" and abs(m) <= k["gegruendet_fenster_monate"]:
            # Gegründet und die EXIST-Förderung endet bzw. endete gerade: jetzt fällt die Anschlussfinanzierung an.
            wann = "endet %s" % e["ende"].strftime("%m/%Y") if m >= 0 else "endete %s" % e["ende"].strftime("%m/%Y")
            return dict(wert=k["gegruendet_wert"], url=rf[2], aussage="Gegründet (%s), %s %s – Anschlussfinanzierung steht an" % (rf[0], prog, wann))
        wann = ("endet %s (in %s)" % (e["ende"].strftime("%m/%Y"), "1 Monat" if m == 1 else "%d Monaten" % m) if m > 0 else
                "endet %s" % e["ende"].strftime("%m/%Y") if m == 0 else "endete %s (%s)" % (e["ende"].strftime("%m/%Y"), vor_monaten(-m)))
        fenster = " – Gründungsfenster" if -6 <= m <= 6 else ""
        return dict(wert=stufe(k["stufen"], m), url=e["url"], datum=e["ende"].isoformat() if e["ende"] <= self.stichtag else None,
                    aussage="%s %s%s" % (prog, wann, fenster))

    def k_tech_tiefe(self, k):
        t, url = self.fachtext()
        if not url:
            return None
        mint = next((x for x in (self.fach_treffer(s_, t) for s_ in ("fach_hardware", "fach_software", "fach_wirkstoff", "fach_medizin")) if x), None)
        ex = self.katalog_exist()
        art = ex[0]["art"] if ex else None
        if art == "ef":
            key = "forschungstransfer_mint" if mint else "forschungstransfer"
            url = ex[0]["url"]
        elif mint:
            key = "mint"
        else:
            stelle = " ".join(e["stelle"] or e["empfaenger"] or "" for e in self.katalog()).lower()
            ohne = self.fach_treffer("fach_ohne_tech", stelle) if stelle else None
            if not ohne:
                return None
            key, mint = "ohne_tech", ohne
        aussage = {"forschungstransfer_mint": "EXIST-Forschungstransfer (forschungsbasiert) im Fachgebiet „%s“" % mint,
                   "forschungstransfer": "EXIST-Forschungstransfer (forschungsbasiertes Vorhaben)",
                   "mint": "Technisches Fachgebiet: „%s“" % mint,
                   "ohne_tech": "Fachgebiet ohne Technologiebezug: „%s“" % mint}[key]
        return dict(wert=self.proxy(k["werte"][key]), proxy=True, url=url, aussage=aussage)

    # --- Risiko (1 = hoch) ----------------------------------------------------
    def reifegrad(self):
        return self.enum("reifegrad", self.cfg["kriterien"]["risiko"]["tech_reife"]["werte"])

    def reifegrad_bestaetigt(self):
        """Reifegrad aus mindestens zwei unabhängigen Domains belegt. Ohne Angabe `reifegrad_quellen` (handgepflegtes
        Dossier) gilt der Einzelbeleg wie bisher; die Liste setzt evaluation.engine.to_dossier für die Textklassifikation."""
        q = self.d.get("reifegrad_quellen")
        if not isinstance(q, list):
            return True
        return len({domain(u) for u in q if is_url(u)}) >= 2

    def k_tech_reife(self, k):
        v, url, datum = self.reifegrad()
        if not v:
            return None
        if self.reifegrad_bestaetigt():
            return dict(wert=k["werte"][v], aussage="Reifegrad: %s" % v, url=url, datum=datum)
        return dict(wert=self.proxy(k["werte"][v]), proxy=True, url=url, datum=datum,
                    aussage="Reifegrad: %s (Textklassifikation, nur eine Quelle)" % v)

    def k_regulatorik(self, k):
        v, url, datum = self.dated_fact(self.d.get("regulierter_markt"))
        if not isinstance(v, bool) or not url:
            t, url = self.fachtext()
            med = self.fach_treffer("fach_medizin", t) if url else None
            if not med:  # ohne Medizin-Bezug bleibt die Regulatorik offen, nicht "unreguliert"
                return None
            return dict(wert=self.proxy(k["werte"]["reguliert"]), proxy=True, url=url,
                        aussage="Vermutlich regulierter Markt (Medizin-Bezug: „%s“)" % clip(med, 40))
        return dict(wert=k["werte"]["reguliert" if v else "nicht_reguliert"],
                    aussage="Regulierter Markt, Zulassung nötig" if v else "Kein regulierter Markt", url=url, datum=datum)

    def k_ip(self, k):
        v, url, datum = self.enum("ip", k["werte"])
        if not v:
            return None
        return dict(wert=k["werte"][v], url=url, datum=datum,
                    aussage={"patent_erteilt": "Patent erteilt", "patent_angemeldet": "Patent angemeldet", "keine": "Keine Schutzrechte"}[v])

    def k_finanzierung(self, k):
        mit_summe = [(num(f.get("summe_eur")), f) for f in self.foerderung if num(f.get("summe_eur")) is not None]
        if not mit_summe:
            return None
        summe = min(MAX_ZAHL, sum(s for s, _ in mit_summe))
        erster = mit_summe[0][1]
        # Programm nennen: ein Gründungsstipendium (~100–160 k€, 12 Monate) und ein Forschungstransfer (~0,6–1,5 Mio. €,
        # 18–36 Monate) sind verschiedene Finanzierungslagen, auch wenn die Stufen nur die Summe bewerten.
        programme = list(dict.fromkeys(clip(text(str(f.get("programm") or "")) or "", 60) for _, f in mit_summe))
        programme = [p for p in programme if p]
        zusatz = " (%s)" % ", ".join(programme[:3]) if programme else ""
        return dict(wert=stufe(k["stufen"], summe), aussage="Bisherige Förderung %s EUR%s" % (eur(summe), zusatz), url=erster["quelle"], datum=iso(erster.get("start")))

    def k_datenlage(self, k):
        if not self.signals:
            return None
        n = len({domain(s["url"]) for s in self.signals})
        wert = stufe(k["stufen"], n)
        aussage = ("Dünne Datenlage: nur eine unabhängige Quelle" if n == 1
                   else "Dünne Datenlage: %d unabhängige Quellen" % n if wert >= 0.5 else "%d unabhängige Quellen" % n)
        mc = num(self.d.get("match_confidence"))
        if mc is not None and mc < k["match_confidence_min"]:
            wert, aussage = max(wert, k["wert_bei_unsicherem_match"]), aussage + "; Zuordnung Projekt→Firma laut Sourcing unsicher (%.2f)" % mc
        return dict(wert=wert, aussage=aussage, url=self.signals[0]["url"], datum=self.signals[0]["datum"].isoformat())

    # --- Einordnung -----------------------------------------------------------
    def rechtsform(self):
        """(rechtsform | 'keine' | None, in_gruendung, url). None = nicht belegt."""
        v, url, _ = self.dated_fact(self.d.get("rechtsform"))
        v = text(v)
        if not v or not url:
            return None, False, None
        if v.lower() in ("keine", "keine rechtsform"):
            return "keine", False, url
        # Die Angabe muss mit der Rechtsform enden ("Muster UG (haftungsbeschränkt) i.G."). Verneinungen, Pläne,
        # "AG Müller", e.V., GbR oder "unbekannt" gelten nicht als belegte Kapitalgesellschaft.
        m = re.fullmatch(r"(?:.*[\s])?((?i:g?GmbH)|UG|AG|SE)(?:\s*\((?i:haftungsbeschr(?:ä|ae)nkt)\))?"
                         r"(\s*(?:i\.\s?Gr?\.?|(?i:in\s+Gr(?:ü|ue)ndung)))?", v)
        if not m or re.search(r"(?i)(?<!\w)(kein|keine|noch|nicht|geplant|geplante)(?!\w)", v):
            return None, False, None
        form = {"gmbh": "GmbH", "ggmbh": "gGmbH"}.get(m.group(1).lower(), m.group(1))
        return form + (" i.G." if m.group(2) else ""), bool(m.group(2)), url

    def gruendung(self):
        """(datum, ist_proxy, url, monat_bekannt). Belegtes Gründungsdatum, sonst belegter EXIST-Start als markierter Proxy.

        Ist nur das Jahr bekannt, gilt für die Altersprüfung der 31.12., damit das Alter nie überschätzt wird.
        """
        v, url, _ = self.dated_fact(self.d.get("gruendungsdatum"))
        echt = parse_date(v)
        if echt and url and echt <= self.stichtag:
            if nur_jahr(v):
                return min(dt.date(echt.year, 12, 31), self.stichtag), False, url, False
            return echt, False, url, True
        h = self.hinweis()
        if h:
            return min(dt.date(h[0], 12, 31), self.stichtag), True, h[1], False
        for f in self.exist():
            return parse_date(f["start"]), True, f["quelle"], not nur_jahr(f["start"])
        return None, False, None, False

    def hinweis(self):
        """(jahr, url) aus `gruendungsjahr_hinweis` (Jahr aus einem Pressetext), sonst None.

        Schwächer als ein Register-/Impressumsdatum: zählt nur als Proxy, nie für `zu_spaet`. Liegt das Jahr mehr
        als 24 Monate vor dem ersten Signal, gilt es als Fremdbezug (anderer Artikel, Namensvetter) und wird ignoriert.
        """
        h = self.hinweis_roh()
        return h if h and not self.hinweis_ignoriert() else None

    def hinweis_roh(self):
        v, url, _ = self.dated_fact(self.d.get("gruendungsjahr_hinweis"))
        if isinstance(v, str) and nur_jahr(v):
            v = int(v)
        if isinstance(v, bool) or not isinstance(v, int) or not url or not 1900 <= v <= self.stichtag.year:
            return None
        return v, url

    def hinweis_ignoriert(self):
        """Jahr des Hinweises, wenn es mehr als hinweis_max_vor_signal_monate vor dem ersten Signal liegt."""
        h = self.hinweis_roh()
        if h and self.signals and months_between(dt.date(h[0], 12, 31), self.signals[0]["datum"]) > self.cfg["hinweis_max_vor_signal_monate"]:
            return h[0]
        return None

    def funding(self):
        v, url, _ = self.dated_fact(self.d.get("funding_meldung"))
        return url if v is True and url else None

    def noise(self):
        """(klasse, herkunft, url)."""
        v = self.d.get("noise_class")
        if isinstance(v, str) and v in NOISE:
            return v, "sourcing", None
        if self.funding():
            return "bereits_finanziert", "heuristik", self.funding()
        for feld in ("website_text", "beschreibung_rohtext"):
            wt, url, _ = self.dated_fact(self.d.get(feld))
            if isinstance(wt, str) and url:
                klasse = self.agentur_regel(wt)
                if klasse:
                    return klasse, "heuristik", url
        name, name_url, _ = fact(self.d.get("name_unternehmen"))
        for titel, url in [(text(name), name_url)] + [(e["thema"], e["url"]) for e in self.katalog()]:
            m = re.search(self.cfg["noise_titel_muster"], titel or "") if url else None
            if m:  # Projekttitel benennt eine Dienstleistung ("…beratung", "… Consulting", "…agentur")
                return ("beratung" if re.match(r"(?i)berat|consult", m.group(1)) else "agentur"), "heuristik", url
        repo, url, _ = self.enum("repo_art", ("kurs", "seminar", "hobby", "produkt"))
        if repo in ("kurs", "seminar"):
            return "studi_projekt", "heuristik", url
        if repo == "hobby":
            return "hobby", "heuristik", url
        rf, _, rf_url = self.rechtsform()
        substanz = (self.foerderung or self.enum("ip", ("patent_erteilt", "patent_angemeldet"))[0] or self.k_traktion(self.cfg["kriterien"]["marktpotenzial"]["traktion"])
                    or any(isinstance(m.get("papers_im_feld"), int) and m["papers_im_feld"] > 0 for m in self.team))
        if len(self.team) == 1 and rf == "keine" and not substanz:
            return "hobby", "heuristik", rf_url
        return "vc_potenzial", "heuristik", None

    def agentur_regel(self, wt):
        """'agentur' | 'beratung' | None. Mindestens noise_agentur_min_treffer verschiedene, nicht verneinte Agentur-Wörter,
        davon mindestens ein Kernwort, und weniger Produkt-/Forschungswörter als Agentur-Treffer."""
        cfg, low = self.cfg, wt.lower()
        treffer = [w for w in cfg["noise_agentur_woerter"] if wort_unverneint(w, low)]
        if len(treffer) < cfg["noise_agentur_min_treffer"] or not any(w in cfg["noise_agentur_kernwoerter"] for w in treffer):
            return None
        if sum(wort_in(w, low) for w in cfg["noise_tech_woerter"]) >= len(treffer):
            return None
        beratung = [w for w in treffer if w in cfg["noise_beratung_woerter"]]
        return "beratung" if len(beratung) * 2 >= len(treffer) else "agentur"

    def alt_belegt(self):
        """Belegtes hohes Alter ohne echtes Gründungsdatum -> (grund, url) oder None.

        1. Gründungsjahr aus Pressetext (nicht als Fremdbezug ignoriert) älter als htgf_max_alter_monate, bestätigt durch eine
           belegte Kapitalgesellschaft oder einen Datenbankeintrag laut Sourcing. Ohne Bestätigung nur offener Punkt.
        2. Datenbankprofil (in_databases, first_db_date) älter als htgf_max_alter_monate und höchstens
           hinweis_max_vor_signal_monate vor dem ersten eigenen Signal (sonst Namensvetter).
        """
        cfg, maxm = self.cfg, self.cfg["htgf_max_alter_monate"]
        h = self.hinweis()
        if h and cfg["zu_spaet_wenn_alter_hinweis_bestaetigt"] and months_between(dt.date(h[0], 12, 31), self.stichtag) > maxm:
            bestaetigt = self.hinweis_bestaetigung()
            if bestaetigt:
                return "älter als %d Monate (gegründet %d laut Pressetext, bestätigt durch %s)" % (maxm, h[0], " und ".join(bestaetigt)), h[1]
        db = voll(self.d.get("first_db_date"))
        if (cfg["zu_spaet_wenn_alter_db_eintrag"] and self.d.get("in_databases") is True and not self.d.get("in_databases_konflikt")
                and db and db <= self.stichtag
                and months_between(db, self.stichtag) > maxm
                and (not self.signals or months_between(db, self.signals[0]["datum"]) <= cfg["hinweis_max_vor_signal_monate"])):
            q = self.d.get("in_databases_quelle")
            return "Datenbankprofil seit %s, älter als %d Monate (laut Sourcing)" % (db.strftime("%m/%Y"), maxm), (q if is_url(q) else None)
        return None

    def hinweis_bestaetigung(self):
        rf = self.rechtsform()[0]
        out = ["Rechtsform %s" % rf] if rf and rf != "keine" else []
        if self.d.get("in_databases") is True and not self.d.get("in_databases_konflikt"):
            out.append("Datenbankeintrag")
        return out
    def beyond_age_limit(self, founded):
        raw, _, _ = self.dated_fact(self.d.get("gruendungsdatum"))
        if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}", raw.strip()):
            founded = founded.replace(day=calendar.monthrange(founded.year, founded.month)[1])
        months = self.cfg["htgf_max_alter_monate"]
        year, month = divmod(self.stichtag.year * 12 + self.stichtag.month - 1 - months, 12)
        if year < 1:
            return False
        day = min(self.stichtag.day, calendar.monthrange(year, month + 1)[1])
        return founded < dt.date(year, month + 1, day)

    def stage(self, noise):
        """(stage, grund, url)."""
        cfg = self.cfg
        rf, ig, rf_url = self.rechtsform()
        gr, proxy, gr_url, monat = self.gruendung()
        if self.funding():
            return "zu_spaet", "Finanzierung gemeldet", self.funding()
        if noise == "bereits_finanziert":
            return "zu_spaet", "laut Sourcing bereits finanziert", None
        if self.d.get("in_databases") is True and cfg["zu_spaet_wenn_in_databases"]:
            return "zu_spaet", "bereits in Datenbanken gelistet", text(self.d.get("in_databases_quelle"))
        if gr and not proxy and self.beyond_age_limit(gr):
            return "zu_spaet", "älter als %d Monate (gegründet %s)" % (cfg["htgf_max_alter_monate"], gr.strftime("%m/%Y") if monat else str(gr.year)), gr_url
        alt = None if gr and not proxy else self.alt_belegt()
        if alt:
            return "zu_spaet", alt[0], alt[1]
        if (not rf or rf == "keine") and gr and not proxy:
            return "pre_seed", "gegründet laut Quelle (%s), Rechtsform nicht belegt" % (gr.strftime("%m/%Y") if monat else gr.year), gr_url
        h = self.hinweis()
        if (not rf or rf == "keine") and h and gr_url == h[1]:
            return "pre_seed", "gegründet laut Quelle (Pressetext, %d), Rechtsform nicht belegt" % h[0], h[1]
        if not rf or rf == "keine":
            return "pre_gruendung", "keine Rechtsform belegt", rf_url
        if ig:
            return "in_gruendung", "Rechtsform %s" % rf, rf_url
        if self.reifegrad()[0] in ("pilot", "erste_kunden"):
            # seed nur mit unabhängig bestätigtem Reifegrad oder belegtem Kunden/Piloten, nicht aus einer Textstelle allein
            kunden = [p for p in self.dated_rows(self.d.get("partner")) if p.get("typ") in ("kunde", "pilot") and is_url(p.get("quelle"))]
            if self.reifegrad_bestaetigt() or kunden:
                return "seed", "Rechtsform %s, Reifegrad %s" % (rf, self.reifegrad()[0]), rf_url
            return "pre_seed", "Rechtsform %s; Reifegrad %s nur aus einer Quelle, für seed nicht ausreichend" % (rf, self.reifegrad()[0]), rf_url
        return "pre_seed", "Rechtsform %s" % rf, rf_url

    def db_pruefung(self):
        """'wayback' | 'suche' | None: Art der Datenbankprüfung nach Host der Quelle (web.archive.org = nur Wayback-Snapshots)."""
        q = self.d.get("in_databases_quelle")
        if not is_url(q):
            return None
        return "wayback" if host(q).endswith("web.archive.org") else "suche"

    def email(self, website):
        """Nur generisches Postfach auf der Domain der eigenen Website, mit Quelle."""
        v, url, _ = self.dated_fact(self.d.get("email"))
        v = text(v)
        if not v or not url or not website or not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", v):
            return ""
        lokal, teil = v.lower().split("@")
        return v if lokal in self.cfg["email_erlaubte_postfaecher"] and host("https://" + teil) == host(website) else ""


def pflicht_fehlt(s, name):
    fehlt = []
    if not name:
        fehlt.append("name_unternehmen")
    if not s.rohtext:
        fehlt.append("beschreibung_rohtext (mit Quellen-URL)")
    if not s.signals:
        fehlt.append("signals (mind. 1 mit URL und Datum bis zum Stichtag)")
    de, url, documented = fact(s.d.get("deutschland_beleg"))
    if not text(de) or not url or (documented and documented > s.stichtag.isoformat()):
        fehlt.append("deutschland_beleg (mit Quellen-URL)")
    return fehlt


def _lead_id(d, name):
    roh = d.get("lead_id")
    if isinstance(roh, (str, int)) and not isinstance(roh, bool) and str(roh).strip():
        return clip(str(roh).strip(), 120)
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "lead-" + hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:10]


def _stichtag(stichtag):
    if stichtag is None:
        return dt.date.today()
    d = parse_date(stichtag)
    if not d or (isinstance(stichtag, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stichtag.strip())):
        raise ValueError("stichtag ist kein Datum (JJJJ-MM-TT): %r" % (stichtag,))
    return d


def _leer(lead_id, name, cfg, stichtag):
    return {
        "lead_id": lead_id, "name_gruender": "", "email": "", "name_unternehmen": name or "", "website": "", "branche": None,
        "gruendungsjahr": None, "gruendungsmonat": None, "gruendung_ist_proxy": False,
        "risiko_score": None, "marktpotenzial_score": None, "team_score": None, "gesamt_score": None,
        "confidence": cfg["confidence_ohne_pflichtfelder"], "stage": None, "produktbeschreibung": "", "value_proposition": "",
        "investmenthypothese": "", "why_now": "", "noise_class": None, "noise_quelle": None,
        "status": "zurueck_an_sourcing", "ausschluss_grund": "", "evidence": [], "teilwerte": {}, "offene_punkte": [],
        "first_signal_date": None, "earliness_delta_monate": None, "in_databases": None, "source_url": None,
        "dim3_name": str(cfg["dim3_name"]), "scoring_version": str(cfg["version"]), "stichtag": stichtag.isoformat(),
    }


def score_dossier(dossier, cfg=None, stichtag=None):
    """Ein Dossier -> ein Score-Datensatz (dict, Spalten siehe scores.schema.json). Wirft nie wegen Dossier-Inhalten.

    Unbekannte Dossier-Schlüssel werden ignoriert; die gelesenen Schlüssel stehen in SCORING.md ("Dossier-Felder").
    """
    cfg = cfg or load_config()
    tag = _stichtag(stichtag)
    try:
        return _score(dossier, cfg, tag)
    except Exception as e:  # letzte Sicherung: ein kaputtes Dossier darf den Lauf nicht abbrechen
        d = clean(dossier) if isinstance(dossier, dict) else {}
        rec = _leer(_lead_id(d if isinstance(d, dict) else {}, None), None, cfg, tag)
        logger.exception("Scoring fehlgeschlagen für lead_id=%s", rec["lead_id"])
        rec["ausschluss_grund"] = "Dossier nicht lesbar (%s)" % type(e).__name__
        rec["offene_punkte"] = [rec["ausschluss_grund"]]
        return rec


def _score(dossier, cfg, stichtag):
    s = Scorer(clean(dossier), cfg, stichtag)
    name = text(fact(s.d.get("name_unternehmen"))[0])
    name = clip(name, 200) if name else None
    rec = _leer(_lead_id(s.d, name), name, cfg, stichtag)
    _stammdaten(s, rec)
    fehlt = pflicht_fehlt(s, name)
    if fehlt:
        rec.update(ausschluss_grund="Pflichtangaben fehlen: " + ", ".join(fehlt), offene_punkte=fehlt)
        return rec
    _hinweis_punkte(s, rec)
    if rec["in_databases"] is True and s.d.get("in_databases_konflikt"):
        rec["offene_punkte"].append("Datenbankprofil nur als archivierter Slug, Datenbanksuche ohne Treffer – Namensvetter prüfen")
    if rec["in_databases"] is True and rec["earliness_delta_monate"] is None and rec["first_signal_date"]:
        rec["offene_punkte"].append("Datenbankprofil vorhanden, Eintragsdatum unbekannt – Earliness nicht berechenbar")
    scores, abdeckung, treffer = _bewerte_dimensionen(s, rec)
    if s.mix() is False and len(s.gruender()) >= 2:  # nur wenn das Fehlen belegt ist, nie aus fehlenden Daten
        rec["offene_punkte"].append("Business-Profil im Team nicht belegt – prüfen")
    gruende = _einordnung(s, rec, scores, abdeckung)
    rec["investmenthypothese"] = clip(_investmenthypothese(s, rec, treffer, gruende), 400)
    rec["why_now"] = _why_now(s, rec)
    return rec


# --- Stammdaten: Spalten, die auch ein nicht bewertetes Dossier bekommt --------------
def _stammdaten(s, rec):
    d, stichtag = s.d, s.stichtag
    leiter = [m["name"] for m in s.team if not re.search(r"(?i)(?<!\w)(kein|keine|ehem|ehemalig\w*|former|ex)(?!\w)", str(m.get("rolle") or ""))
              and re.search(r"(?<!\w)(gf|gesch(ä|ae)ftsf(ü|ue)hr\w*|projektleit\w*|(mit)?gr(ü|ue)nder\w*|(co-?)?founder|ceo|cto)(?!\w)", str(m.get("rolle") or ""), re.I)]
    website = fact(d.get("website"))[0]
    website = website if is_url(website) else ""
    gr, proxy, _, monat = s.gruendung()
    first_signal = s.signals[0]["datum"] if s.signals else None
    first_db = voll(d.get("first_db_date"))
    in_db = d.get("in_databases") if isinstance(d.get("in_databases"), bool) else None
    if first_db and first_db > stichtag:
        first_db = None
    delta = None
    if first_signal and not (in_db is True and not first_db):  # Profil ohne Datum: Vorsprung unbekannt, nicht "bis heute"
        delta = max(0, months_between(first_signal, first_db or stichtag))  # DB-Eintrag vor dem ersten Signal: kein Vorsprung
    rec.update({
        # name_gruender ohne Teammitglieder (gruender: false)
        "name_gruender": ";".join(clip(n, 80) for n in (leiter or [m["name"] for m in s.gruender()])), "email": s.email(website), "website": website,
        "branche": s.branche, "gruendungsjahr": gr.year if gr else None, "gruendungsmonat": gr.month if gr and monat else None,
        "gruendung_ist_proxy": bool(gr and proxy), "produktbeschreibung": clip(_produktbeschreibung(s), 300),
        "value_proposition": clip(_value_proposition(s), 200),
        "first_signal_date": first_signal.isoformat() if first_signal else None, "earliness_delta_monate": delta, "in_databases": in_db,
        "source_url": d.get("source_url") if is_url(d.get("source_url")) else (s.signals[0]["url"] if s.signals else None),
    })


def _katalog_satzteile(s):
    """(titel, programm, wo) aus dem führenden Katalog-Eintrag, nur belegte Teile; None ohne Katalog-Eintrag."""
    kat = s.katalog()
    if not kat:
        return None
    e = kat[0]
    name = text(fact(s.d.get("name_unternehmen"))[0])
    titel = e["thema"] or name or ""
    inst, gruppe = kurz_stelle(e["stelle"] or e["empfaenger"])
    if not inst and e["empfaenger"]:
        inst = e["empfaenger"].split(",")[0]
    # lange Institutionsnamen ("Rheinisch-Westfälische Technische Hochschule Aachen") nicht mitten im Wort abschneiden:
    # mit Gruppe (Lehrstuhl) reicht die Gruppe, die Institution nur, wenn sie kurz ist
    wo = (clip(gruppe, 110) + (" (%s)" % inst if inst and len(inst) <= 45 else "")) if gruppe else clip(inst or "", 110)
    return titel, clip(e["programm"] or "Förderprojekt", 60), wo, e


def _website_saetze(s):
    """Inhaltliche Sätze aus dem belegten Website-Text (extraktiv, Reihenfolge der Seite). Verworfen: wiederholte Zeilen
    (Menüs), Seitentitel, Überschriften im Title Case ohne Satzzeichen, zusammengeklebte Menüeinträge, Versalien,
    Cookie-/Rechtstext, Förderhinweis, Handlungsaufforderung. -> Liste (leer ohne Website-Text mit Quelle)."""
    wt, url, _ = s.dated_fact(s.d.get("website_text"))
    tx = s.cfg["texte"]
    if not isinstance(wt, str) or not url or re.search(r"(?i)lorem ipsum", wt):  # Baukasten-Platzhalterseite
        return []
    out, gesehen = [], set()
    wt = re.sub(r"(\w)-\s*\n\s*(?=[a-zäöüß])", r"\1", wt)  # Silbentrennung am Zeilenende: "Werkzeug-\nprobleme"
    zeilen = re.split(r"\s*\n\s*", wt)
    mehrfach = {z for z in zeilen if z and len(z.split()) < 6 and zeilen.count(z) >= 2}  # kurze Menüzeilen in Kopf- und Fußnavigation
    for zeile in zeilen:
        if zeile in mehrfach or re.search(r"\s[|·]\s|\s[—–]\s.*\s[—–|]\s", zeile):  # Menü, Seitentitel "Firma | Claim"
            continue
        for satz in saetze(zeile):
            satz = satz.strip(" →•-–")
            buchstaben = [c for c in satz if c.isalpha()]
            woerter = re.findall(r"[A-Za-zÄÖÜäöüß][\w'’-]+", satz)
            if (len(woerter) < tx["website_min_woerter"] or len(satz) > tx["website_max_zeichen"] or satz[:1].islower()
                    or (not re.search(r"[.!?]$", satz) and sum(w[0].isupper() for w in woerter) >= 0.6 * len(woerter))
                    or len(re.findall(r"[a-zäöüß][A-ZÄÖÜ][a-zäöüß]", satz)) >= 2
                    or re.search(tx["website_verwerfen"], satz, re.I)
                    or (buchstaben and sum(c.isupper() for c in buchstaben) > 0.6 * len(buchstaben))):
                continue
            key = satz.lower()
            if key not in gesehen:
                gesehen.add(key)
                out.append(satz)
    return out


def _website_reihenfolge(s):
    """Ein Satz "we/wir + Produktverb" bzw. "our/unser + Produktwort" (Aussage über das eigene Produkt, nicht über das
    Team) aus den ersten sechs zuerst, dann der Rest in Seitenreihenfolge."""
    web = _website_saetze(s)
    eigen = next((x for x in web[:6] if re.search(s.cfg["texte"]["website_eigenaussage"], x)), None)
    return ([eigen] + [x for x in web if x != eigen]) if eigen else web


def _produktbeschreibung(s):
    """Echter Beschreibungstext: die ersten zwei Sätze. Platzhalter des Sourcings: Website-Text, sonst die Katalogseite."""
    if not s.ist_platzhalter():
        return " ".join(saetze(s.rohtext)[:2])
    web = _website_reihenfolge(s)
    if web:
        return clip(" ".join(web[:2]), 300)
    teile = _katalog_satzteile(s)
    if not teile:
        return s.rohtext
    titel, programm, wo, e = teile
    satz = "„%s“: %s%s" % (titel, programm, " an " + wo if wo else "")
    if e["summe"]:
        satz += ", %s EUR" % eur(e["summe"])
    if e["start"] and e["ende"]:
        satz += ", Laufzeit %s–%s" % (e["start"].strftime("%m/%Y"), e["ende"].strftime("%m/%Y"))
    p = s.fach_produkttyp()
    satz += "." + (" Fachgebiet deutet auf %s." % SKALIERUNG_TEXT[p[0]] if p else "")
    return satz + " Produkt und Zielkunde sind noch nicht belegt."


def _value_proposition(s):
    """Ein Satz Problem -> Lösung -> Nutzen, nur extraktiv: erster inhaltlicher Satz, ein kurzer zweiter wird angehängt."""
    if not s.ist_platzhalter():
        return (saetze(s.rohtext) or [""])[0]
    web = _website_reihenfolge(s)
    if web:
        vp = web[0]
        if len(web) > 1 and len(vp) < 100 and re.search(r"[.!?]$", vp + web[1]) and len(vp) + len(web[1]) + 1 <= 200:
            vp += " " + web[1]
        return vp
    teile = _katalog_satzteile(s)
    if not teile:
        return s.rohtext
    titel, programm, wo, _ = teile
    return "„%s“ – %s-Vorhaben%s; Problem und Nutzen noch nicht belegt." % (titel, programm, " aus " + wo if wo else "")


def _hinweis_punkte(s, rec):
    """Offene Punkte zum Gründungsjahr aus einem Pressetext (genutzt als Proxy oder ignoriert)."""
    gr, proxy, _, _ = s.gruendung()
    h = s.hinweis()
    alt = h and months_between(dt.date(h[0], 12, 31), s.stichtag) > s.cfg["htgf_max_alter_monate"]
    if h and proxy and gr and gr.year == h[0] and alt and s.hinweis_bestaetigung() and s.cfg["zu_spaet_wenn_alter_hinweis_bestaetigt"]:
        pass  # wird als zu_spaet ausgeschlossen, Grund steht in ausschluss_grund
    elif h and proxy and gr and gr.year == h[0] and alt:
        rec["offene_punkte"].append("Gründungsjahr %d aus Pressetext ist älter als %d Monate, aber nicht durch Rechtsform oder "
                                    "Datenbankeintrag bestätigt – vor Kontakt prüfen" % (h[0], s.cfg["htgf_max_alter_monate"]))
    elif h and proxy and gr and gr.year == h[0]:
        rec["offene_punkte"].append("Gründungsjahr %d nur aus Pressetext, nicht für Ausschluss verwendet" % h[0])
    elif s.hinweis_ignoriert() and not (gr and not proxy):
        rec["offene_punkte"].append("Gründungsjahr %d aus Pressetext liegt mehr als %d Monate vor dem ersten Signal, ignoriert"
                                    % (s.hinweis_ignoriert(), s.cfg["hinweis_max_vor_signal_monate"]))


# --- Scoring: drei Achsen aus den Kriterien der Konfiguration -------------------------
def _bewerte_dimensionen(s, rec):
    """Füllt evidence, teilwerte und offene_punkte. -> (scores, abdeckung, treffer) je Dimension bzw. (dim, krit)."""
    neutral = s.cfg["neutral"] / 100.0
    scores, abdeckung, treffer = {}, {}, {}
    for dim in DIMENSIONEN:
        total, belegt_gewicht, rec["teilwerte"][dim] = 0.0, 0.0, {}
        for krit, k in s.cfg["kriterien"][dim].items():
            r = getattr(s, "k_" + krit)(k)
            belegt = bool(r and r.get("url") and r.get("wert") is not None)
            if belegt:
                wert = float(r["wert"])
                # Proxy (Institut, Fachgebiet): zählt für die Confidence nur anteilig
                belegt_gewicht += k["gewicht"] * (s.cfg["katalog"]["confidence_faktor"] if r.get("proxy") else 1.0)
                treffer[(dim, krit)] = r
                r["aussage"] = clip(r["aussage"] + (" (Proxy)" if r.get("proxy") else ""), 300)
                rec["evidence"].append({"dimension": dim, "kriterium": krit, "aussage": r["aussage"], "url": r["url"],
                                        "datum": r.get("datum"), "punkte": r1(wert * 100)})
            else:
                wert = neutral
                rec["evidence"].append({"dimension": dim, "kriterium": krit, "aussage": "keine Daten – neutral gesetzt",
                                        "url": None, "datum": None, "punkte": r1(wert * 100)})
                rec["offene_punkte"].append("Kein Beleg für: %s" % KRITERIUM_LABEL[krit])
            total += k["gewicht"] * wert
            rec["teilwerte"][dim][krit] = {"punkte": r1(wert * 100), "gewicht": k["gewicht"], "belegt": belegt,
                                           "proxy": bool(belegt and r.get("proxy"))}
        scores[dim], abdeckung[dim] = r1(total * 100), belegt_gewicht
    return scores, abdeckung, treffer


# --- Klassifikation: Gesamtscore, Confidence, Noise, Stage, Ausschluss -----------------
def _einordnung(s, rec, scores, abdeckung):
    """Setzt Scores, Confidence, Stage, Noise und Status. -> Liste der Ausschlussgründe (leer = kein Ausschluss)."""
    cfg, d = s.cfg, s.d
    g = cfg["gewichte"]
    gesamt = g["team"] * scores["team"] + g["marktpotenzial"] * scores["marktpotenzial"] + g["risiko_invers"] * (100 - scores["risiko"])
    conf = g["team"] * abdeckung["team"] + g["marktpotenzial"] * abdeckung["marktpotenzial"] + g["risiko_invers"] * abdeckung["risiko"]
    mc = num(d.get("match_confidence"))
    if mc is not None:
        conf *= min(1.0, mc)
    elif d.get("match_confidence") is not None:
        rec["offene_punkte"].append("match_confidence nicht lesbar, ignoriert")

    noise, noise_quelle, noise_url = s.noise()
    stage, stage_grund, stage_url = s.stage(noise)
    gruende = []
    if noise != "vc_potenzial":
        gruende.append("noise_class = %s (%s)" % (noise, "laut Sourcing" if noise_quelle == "sourcing" else "Regel"))
        rec["evidence"].append({"dimension": "noise", "kriterium": "noise_class",
                                "aussage": "%s (%s)" % (noise, noise_quelle if noise_url else "laut Sourcing, ohne URL"),
                                "url": noise_url, "datum": None, "punkte": None})
    if stage == "zu_spaet":
        gruende.append("stage = zu_spaet (%s)" % stage_grund)
    if gruende:
        gesamt = min(gesamt, cfg["ausschluss_max_gesamt"])
    if not stage_url:  # Regel ohne Beleg-URL: Sourcing-Metadatum (so benannt) oder ausdrücklich neutral
        stage_grund += " (ohne URL)" if "laut Sourcing" in stage_grund else " – keine Daten, neutral gesetzt"
    rec["evidence"].append({"dimension": "stage", "kriterium": "stage", "aussage": "%s: %s" % (stage, stage_grund),
                            "url": stage_url, "datum": None, "punkte": None})
    rec.update(status="bewertet", risiko_score=scores["risiko"], marktpotenzial_score=scores["marktpotenzial"], team_score=scores["team"],
               gesamt_score=r1(gesamt), confidence=round(min(1.0, conf), 2), stage=stage, noise_class=noise, noise_quelle=noise_quelle,
               ausschluss_grund="; ".join(gruende))
    return gruende


# --- Texte: nur aus Quelltext und belegten Kriterien zusammengesetzt, nichts frei formuliert ---
def _investmenthypothese(s, rec, treffer, gruende):
    cfg = s.cfg
    tx = cfg["texte"]
    risiken = sorted(((cfg["kriterien"]["risiko"][krit]["gewicht"] * r["wert"], r["aussage"]) for (dim, krit), r in treffer.items()
                      if dim == "risiko" and r["wert"] >= tx["risiko_ab"]), key=lambda x: (-x[0], x[1]))
    risiko_satz = "Hauptrisiko: %s." % risiken[0][1] if risiken else "Kein Risikofaktor ab %d Punkten belegt." % round(tx["risiko_ab"] * 100)
    if gruende:
        return "Kein Investment-Case: %s." % rec["ausschluss_grund"]
    staerken = sorted(((cfg["kriterien"][dim][krit]["gewicht"] * r["wert"], r["aussage"]) for (dim, krit), r in treffer.items()
                       if dim != "risiko" and r["wert"] >= tx["staerke_ab"]), key=lambda x: (-x[0], x[1]))[:2]
    reife = s.reifegrad()[0]
    fe = s.foerderende()
    if reife:
        kunde = any(p["typ"] == "kunde" for p in s.partner_geprueft(cfg["kriterien"]["marktpotenzial"]["traktion"])[0])
        if reife == "erste_kunden" and not (kunde or s.reifegrad_bestaetigt()):
            # "erste Kunden" nur aus einer Textstelle: wiederholbarer Vertrieb wäre ein Schritt zu weit
            meilenstein = "Nächster Meilenstein: ein belegter zahlender Kunde."
        else:
            meilenstein = "Nächster Meilenstein: %s." % NAECHSTER_MEILENSTEIN[reife]
    elif fe and fe[0] >= 0 and rec["stage"] in ("pre_gruendung", "in_gruendung"):
        meilenstein = "Wenn bis Förderende %s die Gründung gelingt, ist das Team ein Pre-Seed-Kandidat." % fe[1]["ende"].strftime("%m/%Y")
    else:
        meilenstein = ""
    if rec["confidence"] < tx["hypothese_min_confidence"]:
        belegt = " Belegt: %s." % "; ".join(x[1] for x in staerken) if staerken else ""
        return " ".join(x for x in ("Datenlage zu dünn für eine Hypothese (Confidence %.2f).%s" % (rec["confidence"], belegt),
                                    meilenstein, risiko_satz) if x)
    teile = ["Wir investieren, weil: %s." % "; ".join(x[1] for x in staerken) if staerken
             else "Noch keine Stärke belegt, die Hypothese ist offen."]
    if meilenstein:
        teile.append(meilenstein)
    teile.append(risiko_satz)
    return " ".join(teile)


def vor_monaten(n):
    """Abstand in Monaten als Text: 'in diesem Monat', 'vor 1 Monat', 'vor 5 Monaten'."""
    if n <= 0:
        return "in diesem Monat"
    return "vor 1 Monat" if n == 1 else "vor %d Monaten" % n


def _why_now(s, rec):
    stichtag, tx = s.stichtag, s.cfg["texte"]
    now = [STAGE_TEXT[rec["stage"]]]
    for f in s.exist():
        ende = parse_date(f.get("ende"))
        if ende and ende < stichtag:  # exist() enthält nur Förderungen, die höchstens exist_nachlauf_monate vorbei sind
            now.append("%s endete %s" % (clip(str(f["programm"]), 60), ende.strftime("%m/%Y")))
            break
        if ende and months_between(stichtag, ende) <= tx["foerderende_in_monaten"]:
            now.append("%s endet %s" % (clip(str(f["programm"]), 60), ende.strftime("%m/%Y")))
            break
        if ende:
            now.append("%s läuft bis %s" % (clip(str(f["programm"]), 60), ende.strftime("%m/%Y")))
            break
    else:
        fe = s.foerderende()
        if fe and fe[0] < -s.cfg["exist_nachlauf_monate"]:  # lange vorbei: Gründung oder Abbruch, Status offen
            now.append("%s lief bis %s – Status prüfen" % (clip(fe[1]["programm"] or "EXIST", 60), fe[1]["ende"].strftime("%m/%Y")))
    pruefung = s.db_pruefung()
    if rec["in_databases"] is False:
        # Nur eine echte Datenbanksuche darf "nicht gefunden" sagen; Wayback prüft nur archivierte Profil-Slugs
        now.append({"suche": "in Crunchbase/Dealroom/PitchBook/Tracxn nicht gefunden (Datenbanksuche)",
                    "wayback": "kein archiviertes Crunchbase-/Dealroom-Profil (Wayback)"}.get(pruefung, "laut Sourcing kein Datenbankprofil gefunden"))
    elif rec["in_databases"] is True and s.d.get("in_databases_konflikt"):
        now.append("Crunchbase-/Dealroom-Slug im Webarchiv, Datenbanksuche ohne Profil – Namensvetter prüfen")
    elif rec["in_databases"] is True and rec["stage"] != "zu_spaet":
        q = s.d.get("in_databases_quelle")
        wo = " (archiviertes Profil, Wayback)" if is_url(q) and host(q).endswith("web.archive.org") else " (%s)" % host(q) if is_url(q) else " laut Sourcing"
        now.append("bereits mit Datenbankprofil gelistet%s – Vorsprung prüfen" % wo)
    now.append("jüngstes Signal %s" % vor_monaten(months_between(s.signals[-1]["datum"], stichtag)))
    return "; ".join(now)


def score_all(dossiers, cfg=None, stichtag=None, *, scorer=score_dossier):
    cfg = cfg or load_config()
    tag = _stichtag(stichtag)
    rows = [scorer(d, cfg, tag) for d in (dossiers if isinstance(dossiers, list) else [])]
    vergeben = set()
    for r in rows:  # doppelte IDs brechen den Lauf nicht ab, bleiben aber sichtbar
        if r["lead_id"] in vergeben:
            n, alt = 2, r["lead_id"]
            while "%s-dup%d" % (alt, n) in vergeben or any(x["lead_id"] == "%s-dup%d" % (alt, n) for x in rows):
                n += 1
            r["offene_punkte"] = r["offene_punkte"] + ["lead_id doppelt im Input: %s" % alt]
            r["lead_id"] = "%s-dup%d" % (alt, n)
        vergeben.add(r["lead_id"])
    rows.sort(key=lambda r: (r["gesamt_score"] is None, -(r["gesamt_score"] or 0), r["lead_id"]))
    return rows
