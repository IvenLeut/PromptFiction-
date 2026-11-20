"""Step 1 mapping: Förderkatalog rows -> projects -> RawLead (name, industry/HTGF sector, priority, signals).

The export client lives in sourcing/foekat_export.py.

Industry classification (`classify`) and its basis
--------------------------------------------------
`Industry` has five values and `RawLead.industry` is required, so every lead carries one. How reliable it
is, is recorded as the classification *basis*:

* ``"thema"``    a keyword rule matched the project title (Thema) -> reliable, `htgf_sector` is set;
* ``"institut"`` no title hit, but the executing unit (Ausführende Stelle) or, failing that, the recipient
                 matched -> weak (the institute says little about the product), `htgf_sector` is set;
* ``"default"``  nothing matched -> programme default (03EF Industrial / DeepTech, 03EG AI / Software),
                 `htgf_sector` None and the hint ``industry_unclassified``.

Keywords match whole tokens only (text is lower-cased and split at non-letters and CamelCase, so
"MAXCarbon" -> max, carbon). A keyword ``stem`` matches tokens that start with it, ``*stem`` also matches
inside a German compound ("Hautkrebs" -> *krebs), ``<tok>`` only the exact token and ``a b`` consecutive
tokens. Weak keywords (``carbon``) count only together with another hit of the same rule. Within the first
field with any hit the rule with the most hits wins; ties go to the earlier rule in ``TIE_ORDER`` (FinTech,
HealthTech, ClimateTech, Chemie/Materialien, Industrial/DeepTech, AI/Software: specific domains before the
horizontal software rule, so "KlimaPay" or "AI-Wallet" is FinTech).

Unclassified leads, two deliberate defaults: `sourcing.engine.search` (the pipeline provider) returns only
"thema" and "institut" leads as members of an industry ("thema" first) and default-classified leads only with
``search(..., include_unclassified=True)``; the CLI shortlist (`python -m sourcing foekat`) includes them by
default (hint ``industry_unclassified``) so step 2 can still check them, ``--no-unclassified`` drops them.

Priority
--------
Every lead gets a deterministic integer ``priority`` (0-100, weights in ``PRIORITY_WEIGHTS``) relative to a
reference date ``as_of`` (default: the latest retrieval time of the export rows used, never `date.today()`,
so a rerun from the cache is identical). Leads are sorted by priority desc, project start desc, id.
`prioritization_reason` is one German sentence with the reasons; the machine-readable hints are the labelled
line ``Hinweise: …`` in each signal's evidence and `SourcingRun.info[lead.id]`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from context.cache import Cache
from context.foekat import detail_url
from models import Industry, RawLead, SourceSignal
from research_models import Evidence
from sourcing.foekat_export import (ACADEMIC, DEFAULT_PREFIXES, DEFAULT_SINCE, LEGAL_FORM, PROGRAMMES, SIGNAL_SOURCE,
                                    SIGNAL_TYPE, SOURCE_NAME, ExportResult, GrantRow, _now, export_rows, format_euro)

logger = logging.getLogger(__name__)

# --- priority weights (one place) -----------------------------------------------------------------

PRIORITY_WEIGHTS = {
    "programme_03EF": 40,          # EXIST-Forschungstransfer: research team with a fundable technology
    "end_near_founding": 25,       # funding ends within [as_of - 12 months, as_of + 6 months]: founding moment
    "running": 10,                 # funding runs more than 6 months after as_of
    "ended_long_ago": 0,           # funding ended more than 12 months before as_of
    "basis_thema": 15,
    "basis_institut": 5,
    "amount_500k": 10,             # total federal share >= 500.000 EUR
    "amount_100k": 5,              # total federal share >= 100.000 EUR
    "recipient_company": 10,       # recipient is a company, not a university
}
END_WINDOW_BEFORE_MONTHS, END_WINDOW_AFTER_MONTHS = 12, 6
BASIS_ORDER = {"thema": 0, "institut": 1, "default": 2}
GRANT_APPROVED = "Bewilligt"       # scoring_input.GRANT_STATES["approved"]: the catalogue lists approved grants

# --- industry rules -------------------------------------------------------------------------------

# (rule, Industry, htgf_sector, keywords). Syntax: 'stem' = token starts with stem, '*stem' = stem anywhere in a
# token (compounds), '<tok>' = exact token, 'a b' = consecutive tokens (each a stem).
INDUSTRY_RULES = (
    ("fintech", Industry.FINTECH, "digital_tech", (
        "finanz", "finance", "fintech", "<bank>", "banking", "*versicher", "insur", "payment", "<pay>", "zahlung",
        "blockchain", "krypto", "crypto", "wallet", "accounting", "buchhalt", "rechnungswesen", "steuerrecht",
        "steuerberat", "taxation", "<tax>", "kredit", "<geld>")),
    ("health", Industry.HEALTH, "life_sciences", (
        "*medizin", "*klinik", "charité", "pharma", "gesundheit", "health", "medical", "medicine", "biotech",
        "biomed", "biochem", "molekularbiolog", "zellbiolog", "mikrobiolog", "*immun", "onkolog", "*krebs",
        "cancer", "*therap", "*diagnos", "patient", "pflege", "neurolog", "neurodegen", "neurochirurg",
        "neurowissen", "kardio", "dental", "<zahn>", "zahnmedizin", "zahnarzt", "zahnersatz", "zahnheil",
        "orthop", "orthodont", "chirurg", "surg", "virolog", "infekt", "genom", "protein", "life science",
        "transfusion", "zelltechn", "wirkstoff", "arznei", "medikament", "<hno>", "radiolog", "prothes",
        "rehabilit", "physio", "antibiot", "impfstoff", "*implantat")),
    ("climate", Industry.CLIMATE, "climate_tech", (
        "*energie", "energy", "*klima", "climate", "solar", "photovolt", "*wasserstoff", "hydrogen", "batter",
        "*umwelt", "environment", "nachhaltig", "sustainab", "recyc", "kreislauf", "circular", "emission",
        "<co2>", "<carbon>", "decarbon", "dekarbon", "agrar", "agri", "landwirt", "gartenbau", "forstw",
        "elektrochem", "*elektrolys", "wärmepump", "<pv>", "elektromobil", "biogas", "abwasser")),
    ("chemistry_materials", Industry.INDUSTRIAL, "chemie_materialien", (
        "chemie", "chemistry", "chemical", "chemisch", "*werkstoff", "material", "polymer", "*kunststoff",
        "makromolekular", "*katalys", "keramik", "kolloid", "grenzfläche", "<glas>", "metallurg", "beschicht",
        "*legierung", "nanopartik", "faserverbund", "*klebstoff")),
    ("industrial_deeptech", Industry.INDUSTRIAL, "industrial_deep_tech", (
        "maschinen", "*maschinenbau", "mechanical", "mechanik", "ingenieur", "produktion", "production",
        "fertigung", "manufactur", "robot", "automatisier", "automation", "elektrotechn", "electrical",
        "elektronik", "electronic", "photon", "*laser", "optik", "optics", "optisch", "lichttechn", "physik",
        "physics", "quanten", "quantum", "raumfahrt", "aerospace", "<space>", "satellit", "flugzeug", "fahrzeug",
        "automotive", "mobilität", "mobility", "logistik", "fördertechn", "*sensor", "messtechn", "halbleiter",
        "semiconductor", "mechatron", "mikrosystem", "leichtbau", "verfahrenstechn", "werkzeug", "umformtechn",
        "antrieb", "*getriebe", "bauingenieur", "bauwesen", "architektur", "geophysik", "drohne", "drone",
        "adaptronik", "additiv", "schweiß")),
    ("software_ai", Industry.AI, "digital_tech", (
        "informatik", "computer", "computing", "software", "<ki>", "künstlich intelligenz", "artificial intelligence",
        "<ai>", "machine learning", "maschinell lern", "deep learning", "neuronal netz", "neural network", "data science",
        "daten", "<data>", "digital", "informations", "cyber", "<app>", "cloud", "algorithm", "telematik", "<xr>",
        "<vr>", "virtual reality", "<llm>", "chatbot", "<saas>", "<api>", "sprachmodell", "sprachverarbeit")),
)
TIE_ORDER = tuple(rule for rule, *_ in INDUSTRY_RULES)   # table order is the tie-break order
WEAK_KEYWORDS = {"climate": {"carbon"}}                    # count only together with another hit of the rule
DEFAULT_INDUSTRY = {"03EF": Industry.INDUSTRIAL, "03EG": Industry.AI}
_TOKEN = re.compile(r"[a-z0-9äöüßéè]+")

# --- person names ---------------------------------------------------------------------------------

_TITLE = (r"(?:Jun\.-Prof\.|apl\.\s?Prof\.|Prof\.|Professorin|Professor|Priv\.-Doz\.|PD|"
          r"Dr\.(?:\s?-\s?Ing\.|-Ing\.|\s?rer\.\s?nat\.|\s?med\.(?:\s?dent\.)?|\s?phil\.)?|habil\.|h\.\s?c\.|"
          r"Dipl\.-[A-Za-zäöü]+\.?)")
_NAMEWORD = r"(?:[A-ZÄÖÜ][a-zäöüßéèáçñ]+(?:-[A-ZÄÖÜ][a-zäöüßéèáçñ]+)?|[A-Z]\.)"
_PERSON = re.compile(rf"(?:\b(?:Herr|Frau|Professur)\s+)?(?:{_TITLE}\s*)+(?:(?:von|van|de|zu)\s+)?{_NAMEWORD}"
                     rf"(?:\s+(?:(?:von|van|de|der|zu)\s+)?{_NAMEWORD}){{0,2}}(?![\w-])")
# Untitled working-group head ("..., AG Vorname [Zweitname] van Nachname"): AG + two or three name words (optional
# particle) closing the field or a ',', ';', ' - ' segment, only in an academic field (so "Siemens AG Corporate
# Technology" keeps its legal form). Subject designations ("AG Künstliche Intelligenz", "AG Data Science") are told
# apart by an adjective/English first word or a subject-noun last word (`_is_subject`); a single word
# ("AG Photonik") is never stripped.
_UNTITLED_AG = re.compile(rf"\bAG\s+({_NAMEWORD})(?:\s+{_NAMEWORD})?\s+(?:(?:von|van|de|der|zu)\s+)?({_NAMEWORD})"
                          r"(?=\s*(?:$|[,;|)]|\s[-–]\s))")
_ADJECTIVE_END = re.compile(r"(?:lich|liche|isch|ische|ale|ive|are|elles|ches|ue)$")
_SUBJECT_FIRST = {"data", "quantum", "soft", "applied", "computational", "digital", "neue", "angewandte"}
_SUBJECT_END = re.compile(r"(?:ung|heit|keit|enz|anz|ik|ie|ion|tät|schaft|logie|ismus|tur|systeme|wesen|lehre|"
                          r"kunde|medizin|ence|ance|ics|ogy|ing|nen|ien|ität)$")
# Chairs named after a person ("Dr. Theo Schöller-Stiftungslehrstuhl") are a designation, not a person.
_NAMED_CHAIR = re.compile(r"(?:Dr\.\s+)?(?:[A-ZÄÖÜ][\wäöüß]+\s+){0,2}[A-ZÄÖÜ][\wäöüß]+-(?:Stiftungs)?"
                          r"(?:[Ll]ehrstuhl|[Pp]rofessur|Institut|Zentrum)")


def _is_subject(first: str, last: str) -> bool:
    """'Künstliche Intelligenz' is a subject, 'Erika Musterfrau' a person (heuristic, see _UNTITLED_AG)."""
    first = first.lower()
    return bool(first in _SUBJECT_FIRST or _ADJECTIVE_END.search(first) or _SUBJECT_END.search(last.lower()))


def _strip_untitled_ag(text: str) -> str:
    """Drop untitled 'AG <first> <last>' heads from an academic field (see _UNTITLED_AG)."""
    if not ACADEMIC.search(text):
        return text
    return _UNTITLED_AG.sub(lambda m: m.group(0) if _is_subject(m.group(1), m.group(2)) else " ", text)


def strip_persons(text: str) -> str:
    """Remove personal names with academic titles and untitled 'AG <first> <last>' heads, keep the
    institute/chair designation.

    'Universität X, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau'
    -> 'Universität X, Lehrstuhl für Experimentalphysik VI'."""
    if not text or not (re.search(_TITLE, text) or _UNTITLED_AG.search(text)):
        return text or ""
    chairs: list[str] = []

    def protect(m: re.Match) -> str:
        chairs.append(m.group(0))
        return "\x00%d\x00" % (len(chairs) - 1)
    out = _NAMED_CHAIR.sub(protect, text)
    out = _PERSON.sub(" ", out)
    out = _strip_untitled_ag(out)
    out = re.sub(r"\(\s*[,;|]?\s*\)", " ", out)
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s+([,;)])", r"\1", out)
    out = re.sub(r"([,;|])(?:\s*[,;|])+", r"\1", out)
    out = re.sub(r"(?:\s*[-–,;|]\s*)+$", "", out)
    out = re.sub(r"^(?:\s*[-–,;|]\s*)+", "", out)
    out = re.sub(r"\s+-\s*([,;|])", r"\1", out)
    out = re.sub(r"\s([-–])(?:\s+[-–])+\s", r" \1 ", out)
    out = re.sub(r"\x00(\d+)\x00", lambda m: chairs[int(m.group(1))], out)
    return out.strip() or text


# --- project grouping, name -----------------------------------------------------------------------

_PREFIX = re.compile(r"^\s*(?:EXIST|EFT)[\s_\-]*(?:Forschungstrans?fer|Gr(?:ü|ue)ndungsstipendium)\s*[:\-–]\s*", re.I)
_ALIAS_WORD = r"(?:ehemals|ehem\.|vormals|formerly)"
_ALIAS_PAREN = re.compile(rf"\s*\(\s*{_ALIAS_WORD}\s+([^)]+?)\s*\)\s*$", re.I)
# Unparenthesised alias only after a dash/comma or after a capitalised (name-like) word: 'JoulyAI ehemals Minmo',
# not 'Lernplattform für ehemals Inhaftierte'.
_ALIAS_BARE = re.compile(rf"(\s*[,\-–]\s*|\s+){_ALIAS_WORD}\s+([^()]+?)\s*$", re.I)


def project_name(thema: str) -> tuple[str, str | None]:
    """Thema -> (name, former name). Strips an 'EXIST-Forschungstransfer:'-style prefix and '(ehemals X)'.

    'EXIST-Forschungstransfer: HAPPY' -> ('HAPPY', None); 'u/press (ehemals trykk)' -> ('u/press', 'trykk');
    'JoulyAI ehemals Minmo' -> ('JoulyAI', 'Minmo'); 'Lernplattform für ehemals Inhaftierte' stays whole.
    Old long Themas ('X - Entwicklung eines ...') keep the part before ' - ' when that part is short. Nothing
    else is changed; the result is a substring of Thema.
    """
    name = _PREFIX.sub("", thema or "").strip()
    alias = None
    m = _ALIAS_PAREN.search(name)
    if not (m and m.start() > 0):
        m = _ALIAS_BARE.search(name)
        if m and not (m.group(1).strip() or _bare_alias_ok(name[:m.start()])):
            m = None
    if m and m.start() > 0:
        alias, name = m.group(m.lastindex).strip(), name[:m.start()].strip()
    if len(name) > 60 and " - " in name and len(name.split(" - ", 1)[0]) <= 40:
        name = name.split(" - ", 1)[0].strip()
    return (name or (thema or "").strip()), alias


def _bare_alias_ok(before: str) -> bool:
    """'ehemals X' without parentheses/dash is an alias only after a name-like (not lower-case) word."""
    last = before.rsplit(" ", 1)[-1]
    return bool(last) and not last[0].islower()


def project_key(row: GrantRow) -> str:
    """Rows of one project share a key: the Verbund ('Projekt') value, else the FKZ without a trailing letter."""
    if row.projekt and row.projekt.upper() not in {"N", "NEIN"}:
        return "verbund:" + row.projekt.casefold()
    m = re.fullmatch(r"(03E[FG][0-9A-Z]*\d)([A-Z])", row.fkz)
    return m.group(1) if m else row.fkz


def group_projects(rows: list[GrantRow]) -> list[list[GrantRow]]:
    """Rows grouped by `project_key`, each group sorted by FKZ."""
    groups: dict[str, list[GrantRow]] = {}
    for row in rows:
        groups.setdefault(project_key(row), []).append(row)
    return [sorted(g, key=lambda r: r.fkz) for g in groups.values()]


# --- industry mapping -----------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    """Lowercase tokens; CamelCase and digits split ('SherpAI' -> sherp, ai; 'NIXI-AI' -> nixi, ai)."""
    spaced = re.sub(r"(?<=[a-zäöü])(?=[A-ZÄÖÜ])|(?<=[A-ZÄÖÜ])(?=[A-ZÄÖÜ][a-zäöü])", " ", text or "")
    return _TOKEN.findall(spaced.lower())


def _kw_hits(tokens: list[str], kw: str) -> int:
    if kw.startswith("<"):
        return tokens.count(kw[1:-1])
    if kw.startswith("*"):
        return sum(1 for t in tokens if kw[1:] in t)
    parts = kw.split()
    if len(parts) == 1:
        return sum(1 for t in tokens if t.startswith(kw))
    n = len(parts)
    return sum(1 for i in range(len(tokens) - n + 1) if all(tokens[i + j].startswith(p) for j, p in enumerate(parts)))


def _hits(text: str, keywords: tuple[str, ...], rule: str = "") -> list[str]:
    tokens = _tokens(text)
    hits: list[str] = []
    for kw in keywords:
        hits += [kw.strip("<>*")] * _kw_hits(tokens, kw)
    weak = WEAK_KEYWORDS.get(rule, set())
    return hits if any(h not in weak for h in hits) else []


@dataclass(frozen=True)
class IndustryMatch:
    """Result of `classify`: industry, HTGF sector, winning rule and the field/keywords it rests on."""
    industry: Industry
    htgf_sector: str | None
    rule: str
    field: str | None = None
    keywords: tuple[str, ...] = ()
    text: str = ""

    @property
    def unclassified(self) -> bool:
        """No keyword hit anywhere (programme default industry)."""
        return self.field is None

    @property
    def basis(self) -> str:
        """'thema' (project title), 'institut' (executing unit/recipient only) or 'default' (no hit)."""
        return "default" if self.field is None else "thema" if self.field == "Thema" else "institut"


def classify(rows: list[GrantRow]) -> IndustryMatch:
    """First field with any keyword hit decides (Thema, then Ausführende Stelle, then Förderempfänger);
    within it the rule with the most hits wins, ties go to the earlier rule in TIE_ORDER. No hit ->
    programme default (basis 'default', no HTGF sector)."""
    first = rows[0]
    fields = (("Thema", [r.thema for r in rows]), ("Ausführende Stelle", [strip_persons(r.executing) for r in rows]),
              ("Förderempfänger", [strip_persons(r.recipient) for r in rows]))
    for name, values in fields:
        for value in dict.fromkeys(values):
            scored = [(len(h), -i, rule, industry, sector, h) for i, (rule, industry, sector, kws) in enumerate(INDUSTRY_RULES)
                      if (h := _hits(value, kws, rule))]
            if scored:
                _, _, rule, industry, sector, hits = max(scored, key=lambda t: (t[0], t[1]))
                return IndustryMatch(industry, sector, rule, name, tuple(dict.fromkeys(hits)), value)
    return IndustryMatch(DEFAULT_INDUSTRY.get(first.prefix, Industry.INDUSTRIAL), None, "default_" + first.prefix.lower())


# --- priority -------------------------------------------------------------------------------------

def _add_months(day: date, months: int) -> date:
    """`day` shifted by `months`, clamped to the month's last day."""
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month, d)
        except ValueError:
            continue
    raise ValueError(day)


def priority_for(rows: list[GrantRow], match: IndustryMatch, as_of: date) -> tuple[int, list[str]]:
    """Deterministic priority 0-100 and the German reasons it rests on (see PRIORITY_WEIGHTS)."""
    w, first = PRIORITY_WEIGHTS, rows[0]
    score, reasons = 0, [first.programme]
    if first.prefix == "03EF":
        score += w["programme_03EF"]
    end = max((r.end for r in rows if r.end), default=None)
    if end is None:
        reasons.append("Laufzeitende unbekannt")
    elif end > _add_months(as_of, END_WINDOW_AFTER_MONTHS):
        score += w["running"]
        reasons.append("Förderung läuft bis %s" % end.strftime("%m/%Y"))
    elif end >= _add_months(as_of, -END_WINDOW_BEFORE_MONTHS):
        score += w["end_near_founding"]
        reasons.append("Förderung %s %s" % ("endet" if end >= as_of else "endete", end.strftime("%m/%Y")))
    else:
        score += w["ended_long_ago"]
        reasons.append("Förderung endete %s (länger als %d Monate her)" % (end.strftime("%m/%Y"), END_WINDOW_BEFORE_MONTHS))
    if match.basis == "thema":
        score += w["basis_thema"]
        reasons.append("Branche %s aus Projekttitel (%s)" % (match.industry.value, ", ".join(match.keywords)))
    elif match.basis == "institut":
        score += w["basis_institut"]
        reasons.append("Branche %s nur aus %s (schwach; %s)" % (match.industry.value, match.field, ", ".join(match.keywords)))
    else:
        reasons.append("Branche nicht klassifiziert (Programmstandard %s)" % match.industry.value)
    total = _total(rows)
    if total is not None:
        score += w["amount_500k"] if total >= 500_000 else w["amount_100k"] if total >= 100_000 else 0
        reasons.append("%s EUR" % format(int(total.to_integral_value()), ",").replace(",", "."))
    else:
        reasons.append("Fördersumme unbekannt")
    if any(recipient_is_company(r) for r in rows):
        score += w["recipient_company"]
        reasons.append("Empfänger ist ein Unternehmen")
    return min(100, max(0, score)), reasons


def _total(rows: list[GrantRow]) -> Decimal | None:
    amounts = [r.amount for r in rows if r.amount is not None]
    return sum(amounts, Decimal(0)) if amounts else None


# --- RawLead mapping ------------------------------------------------------------------------------

def _fmt(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day else "?"


def _euro(value: Decimal | None) -> str:
    return format_euro(value).replace(" €", " EUR") if value is not None else "unbekannt"


def _place(name: str, ort: str, land: str) -> str:
    return ", ".join(p for p in (strip_persons(name) or "?", ort, land) if p)


def signal_text(row: GrantRow, hints: list[str] | None = None) -> str:
    """Multi-line labelled catalogue values (one per line); the FKZ line lets step 2 resolve exactly this
    grant and 'Öffentliche Förderung' is read by scoring_input as an approved public grant."""
    lines = [
        "Förderkennzeichen: %s" % row.fkz,
        "Programm: %s" % row.programme,
        "Thema: %s" % (strip_persons(row.thema) or "?"),
        "Förderempfänger: %s" % _place(row.recipient, row.recipient_ort, row.recipient_land),
        "Ausführende Stelle: %s" % _place(row.executing, row.executing_ort, row.executing_land),
        "Laufzeit: %s bis %s" % (_fmt(row.start), _fmt(row.end)),
        "Fördersumme: %s" % _euro(row.amount),
        "Öffentliche Förderung: %s" % GRANT_APPROVED,
    ]
    if hints:
        lines.append("Hinweise: %s" % ", ".join(hints))
    return "\n".join(lines)


def recipient_is_company(row: GrantRow) -> bool:
    """EXIST-Forschungstransfer row whose recipient carries a company legal form (not gGmbH) and neither the
    recipient nor the executing unit reads as academic/research (catalogue phase-II pattern, e.g. FKZ 03EFU*).

    Gründungsstipendium (03EG) is always paid through the university, so its recipients are never the team's
    company (private universities such as 'Macromedia GmbH' would be false positives)."""
    return (row.prefix == "03EF" and bool(LEGAL_FORM.search(row.recipient))
            and not ACADEMIC.search(row.recipient + " " + row.executing))


def flags_for(rows: list[GrantRow], match: IndustryMatch, as_of: date | None = None) -> list[str]:
    """Machine-readable hints of one project (listed in each signal's 'Hinweise:' line)."""
    first = rows[0]
    as_of = as_of or max(r.retrieved_at for r in rows).date()
    company = any(recipient_is_company(r) for r in rows)
    flags = ["early_signal_exist", "founding_date_unknown", "founders_unknown"]
    flags.append("recipient_company" if company else "pre_founding_team")
    if not company:
        flags.append("internal_review_case")  # sourcing rule: teams before founding stay internal
    flags.append("industry_basis_" + match.basis)
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
        row.fkz, strip_persons(row.recipient), row.recipient_ort or "?", row.recipient_land or "?",
        row.recipient_staat or "?", strip_persons(row.executing), row.executing_ort or "?", row.executing_land or "?",
        row.executing_staat or "?")
    return Evidence(source=SOURCE_NAME, url=detail_url(row.fkz), field="country", finding=finding[:1000],
                    retrieved_at=row.retrieved_at)


@dataclass(frozen=True)
class LeadInfo:
    """Structured step-1 facts that RawLead has no field for (RawLead forbids extra fields)."""
    lead_id: str
    programme: str
    basis: str
    rule: str
    priority: int
    flags: tuple[str, ...]
    start: date | None
    end: date | None
    amount: Decimal | None

    def sort_key(self) -> tuple[int, int, str]:
        """Priority desc, project start desc, id."""
        return (-self.priority, -(self.start or date.min).toordinal(), self.lead_id)


def lead_id_for(rows: list[GrantRow]) -> str:
    """Stable lead id 'foekat-<project key>' (lower case, no spaces)."""
    return "foekat-" + project_key(sorted(rows, key=lambda r: r.fkz)[0]).lower().replace("verbund:", "verbund-").replace(" ", "-")


def map_project(rows: list[GrantRow], as_of: date | None = None) -> tuple[RawLead, LeadInfo] | None:
    """One project (one or more FKZ) -> (RawLead, LeadInfo); None when no German recipient/unit is shown."""
    rows = sorted(rows, key=lambda r: r.fkz)
    first = rows[0]
    as_of = as_of or max(r.retrieved_at for r in rows).date()
    evidence = next((e for e in map(country_evidence, rows) if e is not None), None)
    if evidence is None:
        logger.info("Förderkatalog %s: kein deutscher Empfänger/Ausführender, übersprungen", first.fkz)
        return None
    name, alias = project_name(strip_persons(first.thema))
    if not name:
        logger.warning("Förderkatalog %s: Thema leer, Lead nach FKZ benannt", first.fkz)
        name = first.fkz
    match = classify(rows)
    flags = flags_for(rows, match, as_of)
    priority, reasons = priority_for(rows, match, as_of)
    start = min((r.start for r in rows if r.start), default=None)
    end = max((r.end for r in rows if r.end), default=None)
    ort = first.executing_ort or first.recipient_ort or None
    lead_id = lead_id_for(rows)
    rest = _PREFIX.sub("", strip_persons(first.thema)).strip()
    detail = rest[len(name):].strip(" -–:;,") if rest.startswith(name) else ""
    if alias:
        detail = re.sub(r"^\(?\s*%s\s+%s\s*\)?" % (_ALIAS_WORD, re.escape(alias)), "", detail, flags=re.I).strip(" -–:;,")
    description = "„%s“%s%s – Projekt im Programm %s." % (
        name, " (ehemals „%s“)" % alias if alias else "", ": " + detail if detail else "", first.programme)
    reason = "Priorität %d: %s." % (priority, "; ".join(reasons))
    signals = [SourceSignal(source=SIGNAL_SOURCE, type=SIGNAL_TYPE, url=detail_url(r.fkz), date=r.start,
                            evidence=signal_text(r, flags)[:2000], subject_lead_id=lead_id) for r in rows]
    lead = RawLead(
        id=lead_id, name=name, description=description, industry=match.industry, country="DE", location=ort,
        source_url=detail_url(first.fkz), source_name=SOURCE_NAME, country_evidence=evidence, is_demo=False,
        website=None, founders=[], contact_email=None, founding_year=None, founding_month=None, has_vc=None,
        signals=signals, prioritization_reason=reason[:1000],
        htgf_sector=match.htgf_sector if match.basis in ("thema", "institut") else None,
    )
    info = LeadInfo(lead_id, first.prefix, match.basis, match.rule, priority, tuple(flags), start, end, _total(rows))
    return lead, info


def lead_from_rows(rows: list[GrantRow], as_of: date | None = None) -> RawLead | None:
    """`map_project` without the LeadInfo."""
    mapped = map_project(rows, as_of)
    return mapped[0] if mapped else None


@dataclass
class SourcingRun:
    """Mapped leads of one run (sorted by `LeadInfo.sort_key`), the export behind them and per-lead facts."""
    leads: list[RawLead]
    export: ExportResult
    skipped_non_de: list[str] = field(default_factory=list)
    info: dict[str, LeadInfo] = field(default_factory=dict)
    as_of: date | None = None

    def stats(self, industry: Industry | None = None, shown: list[RawLead] | None = None) -> dict:
        """JSON-ready run statistics for `shown` (default: the leads of `industry`, or all)."""
        if shown is None:
            shown = [l for l in self.leads if industry is None or l.industry == industry]
        infos = [self.info[l.id] for l in shown]
        flags: dict[str, int] = {}
        for i in infos:
            for flag in i.flags:
                flags[flag] = flags.get(flag, 0) + 1
        by_industry = {i.value: sum(1 for l in shown if l.industry == i) for i in Industry}
        by_basis = {b: sum(1 for i in infos if i.basis == b) for b in BASIS_ORDER}
        industry_by_basis = {b: {ind.value: sum(1 for l in shown if l.industry == ind and self.info[l.id].basis == b)
                                 for ind in Industry} for b in BASIS_ORDER}
        histogram = {"%d-%d" % (lo, lo + 9 if lo < 90 else 100): sum(1 for i in infos if lo <= i.priority < lo + 10
                                                                     or (lo == 90 and i.priority == 100))
                     for lo in range(0, 100, 10)}
        top = [{"id": l.id, "name": l.name, "programme": PROGRAMMES.get(i.programme, (i.programme,))[0],
                "industry": l.industry.value, "basis": i.basis, "end": i.end.isoformat() if i.end else None,
                "amount_eur": float(i.amount) if i.amount is not None else None, "priority": i.priority}
               for l, i in sorted(zip(shown, infos), key=lambda p: p[1].sort_key())[:10]]
        return {
            "source": SOURCE_NAME, "complete": self.export.complete, "warnings": list(self.export.warnings),
            "queries": [q.as_dict() for q in self.export.queries], "as_of": self.as_of.isoformat() if self.as_of else None,
            "rows": len(self.export.rows), "programmes": {p: sum(1 for r in self.export.rows if r.prefix == p) for p in PROGRAMMES},
            "leads": len(shown), "leads_before_industry_filter": len(self.leads),
            "leads_by_programme": {p: sum(1 for i in infos if i.programme == p) for p in PROGRAMMES},
            "skipped_non_de": list(self.skipped_non_de), "industry": by_industry,
            "industry_defaulted": by_basis["default"], "classification_basis": by_basis,
            "industry_by_basis": industry_by_basis, "priority_histogram": histogram, "top10": top,
            "htgf_sector": {s: sum(1 for l in shown if l.htgf_sector == s) for s in
                            sorted({l.htgf_sector for l in shown if l.htgf_sector})},
            "flags": dict(sorted(flags.items())),
        }


def build_leads(result: ExportResult, as_of: date | None = None) -> SourcingRun:
    """Map all projects; `as_of` (reference date for the priority) defaults to the latest row retrieval date."""
    if as_of is None and result.rows:
        as_of = max(r.retrieved_at for r in result.rows).date()
    pairs, skipped = [], []
    for group in group_projects(result.rows):
        mapped = map_project(group, as_of)
        if mapped is None:
            skipped.extend(r.fkz for r in group)
        else:
            pairs.append(mapped)
    pairs.sort(key=lambda p: p[1].sort_key())
    return SourcingRun([l for l, _ in pairs], result, sorted(skipped), {i.lead_id: i for _, i in pairs}, as_of)


def run(prefixes: tuple[str, ...] = DEFAULT_PREFIXES, since: date = DEFAULT_SINCE, *, fetch=None, cache: Cache | None = None,
        clock=_now, as_of: date | None = None) -> SourcingRun:
    """Export, validate, clean and map: the complete step-1 run for the Förderkatalog."""
    return build_leads(export_rows(prefixes, since, fetch=fetch, cache=cache, clock=clock), as_of=as_of)
