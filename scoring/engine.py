"""Bewertungsalgorithmus: Lead-Dossier -> belegter Score-Datensatz.

Deterministisch und regelbasiert. Ein Fakt zählt nur, wenn er selbst eine Quellen-URL trägt
({"wert": ..., "quelle": "https://..."} bzw. "quelle" am Listeneintrag). Es gibt keine Ersatzquellen.
Ohne Beleg geht ein Kriterium neutral (50) ein und senkt die Confidence. Es wird nie geraten.
Läuft mit Python 3.9+, braucht nur PyYAML.

Ohne URL übernommen werden nur vier Metadaten des Sourcing-Schritts, weil sie dessen eigenes
Ergebnis sind: noise_class, match_confidence, in_databases und first_db_date.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import urlparse

import yaml

CONFIG_PATH = Path(__file__).with_name("scoring_config.yaml")
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
    "datenlage": "Datenlage",
}
STAGE_TEXT = {"pre_gruendung": "Noch vor der Gründung", "in_gruendung": "Gerade in Gründung", "pre_seed": "Gegründet, Pre-Seed",
              "seed": "Seed-reif", "zu_spaet": "Zu spät für einen Erstkontakt"}


def load_config(path=None):
    cfg = yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
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
        return re.sub(r"[\x00-\x1f\x7f]", " ", x.encode("utf-8", "replace").decode("utf-8"))[:20000]
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
        for m in dicts(d.get("team")):
            url = next((m[k] for k in ("quelle", "openalex", "openalex_url") if is_url(m.get(k))), None)
            if text(m.get("name")) and url:
                self.team.append(dict(m, name=text(m["name"]).replace(";", ","), _url=url))
        self.team.sort(key=lambda m: (m["name"], m["_url"]))
        roh, roh_url, _ = fact(d.get("beschreibung_rohtext"))
        self.rohtext = text(roh) if roh_url else None
        self.branche = norm_branche(fact(d.get("branche") or d.get("htgf_bereich"))[0])
        self.foerderung, gesehen = [], set()
        def schluessel(f):
            return (str(parse_date(f.get("start")) or "9999"), f["quelle"], str(f.get("programm")), str(num(f.get("summe_eur"))), str(f.get("ende")))
        for f in sorted((f for f in dicts(d.get("foerderung")) if is_url(f.get("quelle"))), key=schluessel):
            if schluessel(f) not in gesehen:  # nur exakt gleiche Einträge zusammenfassen
                gesehen.add(schluessel(f))
                self.foerderung.append(f)
        self.markt = d.get("markt") if isinstance(d.get("markt"), dict) else {}

    def enum(self, feld, erlaubt, quelle=None):
        v, url, datum = fact(quelle if quelle is not None else self.d.get(feld))
        return (v, url, datum) if isinstance(v, str) and v in erlaubt and url else (None, None, None)

    # --- Team (1 = stark) ---------------------------------------------------
    def k_forscher_match(self, k):
        best = None
        for m in self.team:
            p = m.get("papers_im_feld")
            if isinstance(p, int) and not isinstance(p, bool) and 0 <= p <= 100000 and (best is None or p > best[0]):
                best = (p, m["name"], m["_url"])
        if not best:
            return None
        return dict(wert=stufe(k["stufen"], best[0]), aussage="%s: %d Papers im Produktfeld" % (best[1], best[0]), url=best[2])

    def mix(self):
        v, url, _ = fact(self.d.get("mix_tech_business"))
        if isinstance(v, bool) and url:
            return v
        h = [m.get("hintergrund") for m in self.team]
        if "beides" in h or ("tech" in h and "business" in h):
            return True
        if self.team and all(x == "tech" for x in h):
            return False
        return None

    def k_komplementaer(self, k):
        if not self.team:
            return None
        n, mix = len(self.team), self.mix()
        if n == 1:
            key, aussage = "solo", "Ein Gründer belegt"
        elif mix is True:
            key, aussage = "mehrere_mit_mix", "%d Gründer mit Technik und Business" % n
        elif mix is False:
            key, aussage = "mehrere_ohne_business", "%d Gründer, kein Business-Profil" % n
        else:
            key, aussage = "mehrere_mix_unbekannt", "%d Gründer, Profil-Mix unbekannt" % n
        return dict(wert=k["werte"][key], aussage=aussage, url=self.team[0]["_url"])

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
        v, url, datum = fact(self.d.get("vollzeit_signal"))
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

    # --- Marktpotenzial (1 = groß) -------------------------------------------
    def k_marktvolumen(self, k):
        v, url, datum = fact(self.markt.get("volumen_eur"))
        v = num(v)
        if v is None or not url:
            return None
        return dict(wert=stufe(k["stufen"], v), aussage="Marktvolumen %s EUR" % eur(v), url=url, datum=datum)

    def k_traktion(self, k):
        ok = [p for p in dicts(self.d.get("partner")) if isinstance(p.get("typ"), str) and p["typ"] in k["werte"] and is_url(p.get("quelle"))]
        if not ok:
            return None
        best = max(ok, key=lambda p: (k["werte"][p["typ"]], text(p.get("name")) or "", p["quelle"]))
        wert = min(1.0, k["werte"][best["typ"]] + (k["bonus_ab_zwei"] if len(ok) >= 2 else 0))
        return dict(wert=wert, aussage="%d belegte Partner; stärkster: %s (%s)" % (len(ok), clip(text(best.get("name")) or "ohne Namen", 60), best["typ"]),
                    url=best["quelle"], datum=iso(best.get("datum")))

    def k_skalierbarkeit(self, k):
        v, url, datum = self.enum("produkt_typ", k["werte"])
        return dict(wert=k["werte"][v], aussage="Produkttyp: %s" % v, url=url, datum=datum) if v else None

    def k_zielkunde(self, k):
        zk, u1, _ = fact(self.markt.get("zielkunde"))
        zk = text(zk) if u1 else None
        mo, u2, _ = self.enum("modell", ("b2b", "b2c", "b2b2c"), self.markt.get("modell"))
        if not (zk or mo):
            return None
        return dict(wert=k["werte"]["beides" if zk and mo else "eines"],
                    aussage="Zielkunde: %s; Modell: %s" % (clip(zk, 80) if zk else "nicht belegt", mo or "nicht belegt"), url=u1 if zk else u2)

    def k_wettbewerb(self, k):
        ok = sorted((text(w.get("name")), w["quelle"]) for w in dicts(self.d.get("wettbewerber")) if text(w.get("name")) and is_url(w.get("quelle")))
        if not ok:
            return None
        key = "viele" if len(ok) >= k["viele_ab"] else "wenige"
        return dict(wert=k["werte"][key], aussage="%d belegte Wettbewerber: %s" % (len(ok), clip(", ".join(n for n, _ in ok[:3]), 120)), url=ok[0][1])

    # --- Risiko (1 = hoch) ----------------------------------------------------
    def reifegrad(self):
        return self.enum("reifegrad", self.cfg["kriterien"]["risiko"]["tech_reife"]["werte"])

    def k_tech_reife(self, k):
        v, url, datum = self.reifegrad()
        return dict(wert=k["werte"][v], aussage="Reifegrad: %s" % v, url=url, datum=datum) if v else None

    def k_regulatorik(self, k):
        v, url, datum = fact(self.d.get("regulierter_markt"))
        if not isinstance(v, bool) or not url:
            return None
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
        return dict(wert=stufe(k["stufen"], summe), aussage="Bisherige Förderung %s EUR" % eur(summe), url=erster["quelle"], datum=iso(erster.get("start")))

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
        v, url, _ = fact(self.d.get("rechtsform"))
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
        v, url, _ = fact(self.d.get("gruendungsdatum"))
        echt = parse_date(v)
        if echt and url and echt <= self.stichtag:
            if nur_jahr(v):
                return min(dt.date(echt.year, 12, 31), self.stichtag), False, url, False
            return echt, False, url, True
        for f in self.exist():
            return parse_date(f["start"]), True, f["quelle"], not nur_jahr(f["start"])
        return None, False, None, False

    def funding(self):
        v, url, _ = fact(self.d.get("funding_meldung"))
        return url if v is True and url else None

    def noise(self):
        """(klasse, herkunft, url)."""
        v = self.d.get("noise_class")
        if isinstance(v, str) and v in NOISE:
            return v, "sourcing", None
        if self.funding():
            return "bereits_finanziert", "heuristik", self.funding()
        wt, url, _ = fact(self.d.get("website_text"))
        if isinstance(wt, str) and url:
            treffer = [w for w in self.cfg["noise_agentur_woerter"] if wort_in(w, wt.lower())]
            if len(treffer) >= self.cfg["noise_agentur_min_treffer"]:
                beratung = [w for w in treffer if w in self.cfg["noise_beratung_woerter"]]
                return ("beratung" if len(beratung) * 2 >= len(treffer) else "agentur"), "heuristik", url
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

    def beyond_age_limit(self, founded):
        raw, _, _ = fact(self.d.get("gruendungsdatum"))
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
        if (not rf or rf == "keine") and gr and not proxy:
            return "pre_seed", "gegründet laut Quelle (%s), Rechtsform nicht belegt" % (gr.strftime("%m/%Y") if monat else gr.year), gr_url
        if not rf or rf == "keine":
            return "pre_gruendung", "keine Rechtsform belegt", rf_url
        if ig:
            return "in_gruendung", "Rechtsform %s" % rf, rf_url
        if self.reifegrad()[0] in ("pilot", "erste_kunden"):
            return "seed", "Rechtsform %s, Reifegrad %s" % (rf, self.reifegrad()[0]), rf_url
        return "pre_seed", "Rechtsform %s" % rf, rf_url

    def email(self, website):
        """Nur generisches Postfach auf der Domain der eigenen Website, mit Quelle."""
        v, url, _ = fact(self.d.get("email"))
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
    """Ein Dossier -> ein Score-Datensatz (dict, Spalten siehe scores.schema.json). Wirft nie wegen Dossier-Inhalten."""
    cfg = cfg or load_config()
    tag = _stichtag(stichtag)
    try:
        return _score(dossier, cfg, tag)
    except Exception as e:  # letzte Sicherung: ein kaputtes Dossier darf den Lauf nicht abbrechen
        d = clean(dossier) if isinstance(dossier, dict) else {}
        rec = _leer(_lead_id(d if isinstance(d, dict) else {}, None), None, cfg, tag)
        rec["ausschluss_grund"] = "Dossier nicht lesbar (%s)" % type(e).__name__
        rec["offene_punkte"] = [rec["ausschluss_grund"]]
        return rec


def _score(dossier, cfg, stichtag):
    s = Scorer(clean(dossier), cfg, stichtag)
    d = s.d
    name = text(fact(d.get("name_unternehmen"))[0])
    name = clip(name, 200) if name else None
    rec = _leer(_lead_id(d, name), name, cfg, stichtag)
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
    if first_signal:  # DB-Eintrag vor dem ersten Signal heißt: kein Vorsprung
        delta = max(0, months_between(first_signal, first_db or stichtag))
    rec.update({
        "name_gruender": ";".join(clip(n, 80) for n in (leiter or [m["name"] for m in s.team])), "email": s.email(website), "website": website,
        "branche": s.branche, "gruendungsjahr": gr.year if gr else None, "gruendungsmonat": gr.month if gr and monat else None,
        "gruendung_ist_proxy": bool(gr and proxy), "produktbeschreibung": clip(" ".join(saetze(s.rohtext)[:2]), 300),
        "value_proposition": clip((saetze(s.rohtext) or [""])[0], 200),
        "first_signal_date": first_signal.isoformat() if first_signal else None, "earliness_delta_monate": delta, "in_databases": in_db,
        "source_url": d.get("source_url") if is_url(d.get("source_url")) else (s.signals[0]["url"] if s.signals else None),
    })

    fehlt = pflicht_fehlt(s, name)
    if fehlt:
        rec.update(ausschluss_grund="Pflichtangaben fehlen: " + ", ".join(fehlt), offene_punkte=fehlt)
        return rec

    neutral = cfg["neutral"] / 100.0
    scores, abdeckung, treffer = {}, {}, {}
    for dim in DIMENSIONEN:
        total, belegt_gewicht, rec["teilwerte"][dim] = 0.0, 0.0, {}
        for krit, k in cfg["kriterien"][dim].items():
            r = getattr(s, "k_" + krit)(k)
            belegt = bool(r and r.get("url") and r.get("wert") is not None)
            if belegt:
                wert = float(r["wert"])
                belegt_gewicht += k["gewicht"]
                treffer[(dim, krit)] = r
                r["aussage"] = clip(r["aussage"], 300)
                rec["evidence"].append({"dimension": dim, "kriterium": krit, "aussage": r["aussage"], "url": r["url"],
                                        "datum": r.get("datum"), "punkte": r1(wert * 100)})
            else:
                wert = neutral
                rec["evidence"].append({"dimension": dim, "kriterium": krit, "aussage": "keine Daten – neutral gesetzt",
                                        "url": None, "datum": None, "punkte": r1(wert * 100)})
                rec["offene_punkte"].append("Kein Beleg für: %s" % KRITERIUM_LABEL[krit])
            total += k["gewicht"] * wert
            rec["teilwerte"][dim][krit] = {"punkte": r1(wert * 100), "gewicht": k["gewicht"], "belegt": belegt}
        scores[dim], abdeckung[dim] = r1(total * 100), belegt_gewicht

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
        rec["evidence"].append({"dimension": "noise", "kriterium": "noise_class", "aussage": "%s (%s)" % (noise, noise_quelle),
                                "url": noise_url, "datum": None, "punkte": None})
    if stage == "zu_spaet":
        gruende.append("stage = zu_spaet (%s)" % stage_grund)
    if gruende:
        gesamt = min(gesamt, cfg["ausschluss_max_gesamt"])
    rec["evidence"].append({"dimension": "stage", "kriterium": "stage", "aussage": "%s: %s" % (stage, stage_grund),
                            "url": stage_url, "datum": None, "punkte": None})
    rec.update(status="bewertet", risiko_score=scores["risiko"], marktpotenzial_score=scores["marktpotenzial"], team_score=scores["team"],
               gesamt_score=r1(gesamt), confidence=round(min(1.0, conf), 2), stage=stage, noise_class=noise, noise_quelle=noise_quelle,
               ausschluss_grund="; ".join(gruende))

    # Texte: nur aus Quelltext und belegten Kriterien zusammengesetzt, nichts frei formuliert.
    tx = cfg["texte"]
    risiken = sorted(((cfg["kriterien"]["risiko"][krit]["gewicht"] * r["wert"], r["aussage"]) for (dim, krit), r in treffer.items()
                      if dim == "risiko" and r["wert"] >= tx["risiko_ab"]), key=lambda x: (-x[0], x[1]))
    risiko_satz = "Hauptrisiko: %s." % risiken[0][1] if risiken else "Kein Risikofaktor ab %d Punkten belegt." % round(tx["risiko_ab"] * 100)
    if gruende:
        hypo = "Kein Investment-Case: %s." % rec["ausschluss_grund"]
    elif rec["confidence"] < tx["hypothese_min_confidence"]:
        hypo = "Datenlage zu dünn für eine Hypothese (Confidence %.2f). %s" % (rec["confidence"], risiko_satz)
    else:
        staerken = sorted(((cfg["kriterien"][dim][krit]["gewicht"] * r["wert"], r["aussage"]) for (dim, krit), r in treffer.items()
                           if dim != "risiko" and r["wert"] >= tx["staerke_ab"]), key=lambda x: (-x[0], x[1]))[:2]
        teile = ["Wir investieren, weil: %s." % "; ".join(x[1] for x in staerken) if staerken
                 else "Noch keine Stärke belegt, die Hypothese ist offen."]
        reife = s.reifegrad()[0]
        if reife:
            teile.append("Nächster Meilenstein: %s." % NAECHSTER_MEILENSTEIN[reife])
        teile.append(risiko_satz)
        hypo = " ".join(teile)
    rec["investmenthypothese"] = clip(hypo, 400)

    now = [STAGE_TEXT[stage]]
    for f in s.exist():
        ende = parse_date(f.get("ende"))
        if ende and 0 <= months_between(stichtag, ende) <= tx["foerderende_in_monaten"]:
            now.append("%s endet %s" % (clip(str(f["programm"]), 60), ende.strftime("%m/%Y")))
            break
    if in_db is False:
        now.append("in Crunchbase/Dealroom nicht gefunden" if d.get("in_databases_quelle") else "laut Sourcing in keiner Datenbank gefunden")
    now.append("jüngstes Signal vor %d Monaten" % months_between(s.signals[-1]["datum"], stichtag))
    rec["why_now"] = "; ".join(now)
    return rec


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
