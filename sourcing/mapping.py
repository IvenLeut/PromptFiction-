"""Step 1 mapping: Förderkatalog rows -> projects -> RawLead (name, industry/HTGF sector, signals, flags).

The export client lives in sourcing/foekat_export.py. Split out so the two halves can be worked on
and tested independently; `sourcing.foekat_export` re-exports these names for existing callers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from context.cache import Cache
from context.foekat import detail_url
from models import Industry, RawLead, SourceSignal
from research_models import Evidence
from sourcing.foekat_export import *  # noqa: F401,F403  (constants and row types)
from sourcing.foekat_export import (ACADEMIC, DEFAULT_SINCE, LEGAL_FORM, PROGRAMMES, SIGNAL_SOURCE, SIGNAL_TYPE, SOURCE_NAME,
                                    ExportResult, GrantRow, _now, export_rows, format_euro)

# --- project grouping, name -----------------------------------------------------------------------

_PREFIX = re.compile(r"^\s*(?:EXIST|EFT)[\s_\-]*(?:Forschungstrans?fer|Gr(?:ü|ue)ndungsstipendium)\s*[:\-–]\s*", re.I)
_ALIAS = re.compile(r"\s*\(?\s*\b(?:ehemals|ehem\.|vormals|formerly)\s+([^)]+?)\s*\)?\s*$", re.I)


def project_name(thema: str) -> tuple[str, str | None]:
    """Thema -> (name, former name). Strips an 'EXIST-Forschungstransfer:'-style prefix and '(ehemals X)'.

    'EXIST-Forschungstransfer: HAPPY' -> ('HAPPY', None); 'u/press (ehemals trykk)' -> ('u/press', 'trykk');
    'JoulyAI ehemals Minmo' -> ('JoulyAI', 'Minmo'). Old long Themas ('X - Entwicklung eines ...') keep the
    part before ' - ' when that part is short. Nothing else is changed; the result is a substring of Thema.
    """
    name = _PREFIX.sub("", thema or "").strip()
    alias = None
    m = _ALIAS.search(name)
    if m and m.start() > 0:
        alias, name = m.group(1).strip(), name[:m.start()].strip()
    if len(name) > 60 and " - " in name and len(name.split(" - ", 1)[0]) <= 40:
        name = name.split(" - ", 1)[0].strip()
    return (name or (thema or "").strip()), alias


def project_key(row: GrantRow) -> str:
    """Rows of one project share a key: the Verbund ('Projekt') value, else the FKZ without a trailing letter."""
    if row.projekt and row.projekt.upper() not in {"N", "NEIN"}:
        return "verbund:" + row.projekt.casefold()
    m = re.fullmatch(r"(03E[FG][0-9A-Z]*\d)([A-Z])", row.fkz)
    return m.group(1) if m else row.fkz


def group_projects(rows: list[GrantRow]) -> list[list[GrantRow]]:
    groups: dict[str, list[GrantRow]] = {}
    for row in rows:
        groups.setdefault(project_key(row), []).append(row)
    return [sorted(g, key=lambda r: r.fkz) for g in groups.values()]


# --- industry mapping -----------------------------------------------------------------------------

# (rule, Industry, htgf_sector, keywords). Keywords match case-insensitively as substrings, '<kw>' only as
# a whole token. Rule order breaks ties (most specific first, the broad software rule last).
INDUSTRY_RULES = (
    ("health", Industry.HEALTH, "life_sciences", (
        "medizin", "klinik", "charité", "pharma", "gesundheit", "health", "medical", "medicine", "biotech",
        "biolog", "<bio>", "immun", "onkolog", "krebs", "cancer", "therap", "diagnost", "patient", "pflege",
        "neuro", "kardio", "dental", "zahn", "orthop", "orthodont", "chirurg", "surg", "virolog", "infektio",
        "genom", "gentherap", "protein", "life science", "biomedic", "biochemisch", "transfusion", "zelltechn")),
    ("climate", Industry.CLIMATE, "climate_tech", (
        "energie", "energy", "klima", "climate", "solar", "photovolt", "windenerg", "wasserstoff", "hydrogen",
        "batter", "umwelt", "environment", "nachhaltig", "sustainab", "recycling", "kreislauf", "circular",
        "emission", "<co2>", "carbon", "agrar", "agri", "landwirt", "gartenbau", "forstw", "elektrochem")),
    ("fintech", Industry.FINTECH, "digital_tech", (
        "finanz", "finance", "fintech", "<bank>", "banking", "versicherung", "insur", "payment", "zahlungs",
        "blockchain", "krypto", "crypto", "wallet", "accounting", "rechnungswesen", "steuerrecht", "taxation")),
    ("chemistry_materials", Industry.INDUSTRIAL, "chemie_materialien", (
        "chemie", "chemistry", "chemical", "chemisch", "werkstoff", "material", "polymer", "kunststoff",
        "makromolekular", "katalys", "keramik", "kolloid", "grenzfläche", "<glas>", "metallurg")),
    ("industrial_deeptech", Industry.INDUSTRIAL, "industrial_deep_tech", (
        "maschinen", "mechanical", "ingenieur", "produktion", "production", "fertigung",
        "manufactur", "robot", "automatisierung", "automation", "elektrotechnik", "electrical", "elektronik",
        "electronic", "photon", "laser", "optik", "optics", "lichttechn", "physik", "physics", "quanten",
        "quantum", "luft- und raumfahrt", "aerospace", "raumfahrt", "<space>", "flugzeug", "fahrzeug",
        "automotive", "mobilität", "mobility", "logistik", "fördertechnik", "sensor", "messtechnik", "halbleiter",
        "semiconductor", "mechatron", "mikrosystem", "leichtbau", "verfahrenstechnik", "werkzeug",
        "umformtechnik", "antrieb", "bauingenieur", "bauwesen", "architektur", "geophysik", "drohne", "drone")),
    ("software_ai", Industry.AI, "digital_tech", (
        "informatik", "computer", "computing", "software", "<ki>", "künstliche intelligenz",
        "artificial intelligence", "<ai>", "machine learning", "maschinelles lernen", "data science",
        "daten", "<data>", "digital", "informations", "cyber", "<app>", "cloud", "algorithm",
        "telematik", "<xr>", "<vr>", "virtual reality")),
)
DEFAULT_INDUSTRY = {"03EF": Industry.INDUSTRIAL, "03EG": Industry.AI}
_TOKEN = re.compile(r"[a-z0-9äöüß]+")


def _tokens(text: str) -> list[str]:
    """Lowercase tokens; CamelCase and digits split ('SherpAI' -> sherp, ai; 'NIXI-AI' -> nixi, ai)."""
    spaced = re.sub(r"(?<=[a-zäöü])(?=[A-ZÄÖÜ])|(?<=[A-ZÄÖÜ])(?=[A-ZÄÖÜ][a-zäöü])", " ", text or "")
    return _TOKEN.findall(spaced.lower())


def _hits(text: str, keywords) -> list[str]:
    low, tokens, hits = (text or "").lower(), None, []
    for kw in keywords:
        if kw.startswith("<"):
            tokens = tokens if tokens is not None else _tokens(text)
            hits += [kw.strip("<>")] * tokens.count(kw.strip("<>"))
        else:
            hits += [kw] * low.count(kw)
    return hits


@dataclass(frozen=True)
class IndustryMatch:
    industry: Industry
    htgf_sector: str | None
    rule: str
    field: str | None = None
    keywords: tuple[str, ...] = ()
    text: str = ""

    @property
    def unclassified(self) -> bool:
        return self.field is None


def classify(rows: list[GrantRow]) -> IndustryMatch:
    """First field with any keyword hit decides (Thema, then Ausführende Stelle, then Förderempfänger);
    within it the rule with the most hits wins, ties go to the earlier rule. No hit -> programme default."""
    first = rows[0]
    fields = (("Thema", [r.thema for r in rows]), ("Ausführende Stelle", [r.executing for r in rows]),
              ("Förderempfänger", [r.recipient for r in rows]))
    for name, values in fields:
        for value in dict.fromkeys(values):
            scored = [(len(h), -i, rule, industry, sector, h) for i, (rule, industry, sector, kws) in enumerate(INDUSTRY_RULES)
                      if (h := _hits(value, kws))]
            if scored:
                _, _, rule, industry, sector, hits = max(scored, key=lambda t: (t[0], t[1]))
                return IndustryMatch(industry, sector, rule, name, tuple(dict.fromkeys(hits)), value)
    return IndustryMatch(DEFAULT_INDUSTRY.get(first.prefix, Industry.INDUSTRIAL), None, "default_" + first.prefix.lower())


# --- RawLead mapping ------------------------------------------------------------------------------

def _fmt(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day else "?"


def signal_text(row: GrantRow) -> str:
    """Verbatim catalogue values; starts with the FKZ so step 2 resolves exactly this grant."""
    return ("FKZ %s; Programm: %s; Thema: %s; Förderempfänger: %s, %s, %s; Ausführende Stelle: %s, %s, %s; "
            "Laufzeit: %s bis %s; Summe: %s; Leistungsplansystematik: %s %s; Ressort: %s; Förderart: %s") % (
        row.fkz, row.programme, row.thema or "?", row.recipient or "?", row.recipient_ort or "?", row.recipient_land or "?",
        row.executing or "?", row.executing_ort or "?", row.executing_land or "?", _fmt(row.start), _fmt(row.end),
        format_euro(row.amount), row.lps_code, row.lps_text, row.ressort or "?", row.foerderart or "?")


def recipient_is_company(row: GrantRow) -> bool:
    """EXIST-Forschungstransfer row whose recipient carries a company legal form (not gGmbH) and neither the
    recipient nor the executing unit reads as academic/research (catalogue phase-II pattern, e.g. FKZ 03EFU*).

    Gründungsstipendium (03EG) is always paid through the university, so its recipients are never the team's
    company (private universities such as 'Macromedia GmbH' would be false positives)."""
    return (row.prefix == "03EF" and bool(LEGAL_FORM.search(row.recipient))
            and not ACADEMIC.search(row.recipient + " " + row.executing))


def flags_for(rows: list[GrantRow], match: IndustryMatch) -> list[str]:
    first, as_of = rows[0], max(r.retrieved_at for r in rows).date()
    company = any(recipient_is_company(r) for r in rows)
    flags = ["early_signal_exist", "founding_date_unknown", "founders_unknown"]
    flags.append("recipient_company" if company else "pre_founding_team")
    if not company:
        flags.append("internal_review_case")  # Leonard's rule: teams before founding stay internal
    if match.unclassified:
        flags.append("industry_unclassified")
    if len(rows) > 1:
        flags.append("verbund")
    if all(r.end and r.end < as_of for r in rows):
        flags.append("project_finished")
    if any(r.executing_staat and r.executing_staat != "Deutschland" for r in rows):
        flags.append("executing_country_unassigned")
    if first.prefix == "03EF" and company:
        flags.append("exist_ft_phase2_candidate")
    return flags


def country_evidence(row: GrantRow) -> Evidence | None:
    """DE only when the row itself names Germany as Staat of the recipient or the executing unit."""
    if "Deutschland" not in (row.recipient_staat, row.executing_staat):
        return None
    finding = ("Förderkatalog FKZ %s: Förderempfänger %s, Ort %s, Bundesland %s, Staat %s; "
               "Ausführende Stelle %s, Ort %s, Bundesland %s, Staat %s") % (
        row.fkz, row.recipient, row.recipient_ort or "?", row.recipient_land or "?", row.recipient_staat or "?",
        row.executing, row.executing_ort or "?", row.executing_land or "?", row.executing_staat or "?")
    return Evidence(source=SOURCE_NAME, url=detail_url(row.fkz), field="country", finding=finding[:1000],
                    retrieved_at=row.retrieved_at)


def lead_from_rows(rows: list[GrantRow]) -> RawLead | None:
    """One project (one or more FKZ) -> RawLead; None when the catalogue shows no German recipient/unit."""
    rows = sorted(rows, key=lambda r: r.fkz)
    first = rows[0]
    evidence = next((e for e in map(country_evidence, rows) if e is not None), None)
    if evidence is None:
        logger.info("Förderkatalog %s: kein deutscher Empfänger/Ausführender, übersprungen", first.fkz)
        return None
    name, alias = project_name(first.thema)
    match = classify(rows)
    flags = flags_for(rows, match)
    start = min((r.start for r in rows if r.start), default=None)
    end = max((r.end for r in rows if r.end), default=None)
    total = sum((r.amount for r in rows if r.amount is not None), Decimal(0)) if any(r.amount is not None for r in rows) else None
    ort = first.executing_ort or first.recipient_ort or None
    fkzs = ", ".join(r.fkz for r in rows)
    description = "%s-Projekt „%s“ (FKZ %s)%s; Förderempfänger %s; Ausführende Stelle %s%s; Laufzeit %s bis %s; Bundesanteil %s." % (
        first.programme, name, fkzs, " (ehemals „%s“)" % alias if alias else "", first.recipient, first.executing,
        ", " + ort if ort else "", _fmt(start), _fmt(end), format_euro(total))
    if match.unclassified:
        mapping = "Branche %s als Standard für %s (keine Schlüsselwort-Regel traf)" % (match.industry.value, first.programme)
    else:
        mapping = "Branche %s per Regel %s (%s: „%s“, Treffer: %s)" % (
            match.industry.value, match.rule, match.field, match.text[:160], ", ".join(match.keywords))
    reason = "%s seit %s, %s. %s. Flags: %s" % (first.programme, _fmt(start), format_euro(total), mapping, ", ".join(flags))
    signals = [SourceSignal(source=SIGNAL_SOURCE, type=SIGNAL_TYPE, url=detail_url(r.fkz), date=r.start,
                            evidence=signal_text(r)[:2000]) for r in rows]
    return RawLead(
        id="foekat-" + project_key(first).lower().replace("verbund:", "verbund-").replace(" ", "-"),
        name=name, description=description, industry=match.industry, country="DE", location=ort,
        source_url=detail_url(first.fkz), source_name=SOURCE_NAME, country_evidence=evidence, is_demo=False,
        website=None, founders=[], contact_email=None, founding_year=None, founding_month=None, has_vc=None,
        signals=signals, prioritization_reason=reason[:1000], htgf_sector=match.htgf_sector,
    )


def lead_sort_key(lead: RawLead):
    start = min((s.date for s in lead.signals if s.date), default=date.min)
    return (-start.toordinal(), lead.id)


@dataclass
class SourcingRun:
    leads: list[RawLead]
    export: ExportResult
    skipped_non_de: list[str] = field(default_factory=list)

    def stats(self, industry: Industry | None = None) -> dict:
        shown = [l for l in self.leads if industry is None or l.industry == industry]
        flags: dict[str, int] = {}
        for lead in shown:
            for flag in (lead.prioritization_reason or "").rsplit("Flags: ", 1)[-1].split(", "):
                flags[flag] = flags.get(flag, 0) + 1
        by_industry = {i.value: sum(1 for l in shown if l.industry == i) for i in Industry}
        return {
            "source": SOURCE_NAME, "complete": self.export.complete, "warnings": list(self.export.warnings),
            "queries": [q.as_dict() for q in self.export.queries],
            "rows": len(self.export.rows), "programmes": {p: sum(1 for r in self.export.rows if r.prefix == p) for p in PROGRAMMES},
            "leads": len(shown), "leads_before_industry_filter": len(self.leads),
            "skipped_non_de": list(self.skipped_non_de), "industry": by_industry,
            "industry_defaulted": flags.get("industry_unclassified", 0),
            "htgf_sector": {s: sum(1 for l in shown if l.htgf_sector == s) for s in
                            sorted({l.htgf_sector for l in shown if l.htgf_sector})},
            "flags": dict(sorted(flags.items())),
        }


def build_leads(result: ExportResult) -> SourcingRun:
    leads, skipped = [], []
    for group in group_projects(result.rows):
        lead = lead_from_rows(group)
        if lead is None:
            skipped.extend(r.fkz for r in group)
        else:
            leads.append(lead)
    leads.sort(key=lead_sort_key)
    return SourcingRun(leads, result, sorted(skipped))


def run(prefixes=("03EF", "03EG"), since: date = DEFAULT_SINCE, *, fetch=None, cache: Cache | None = None,
        clock=_now) -> SourcingRun:
    """Export, validate, clean and map: the complete step-1 run for the Förderkatalog."""
    return build_leads(export_rows(prefixes, since, fetch=fetch, cache=cache, clock=clock))
