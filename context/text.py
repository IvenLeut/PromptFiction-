"""Text helpers shared by the context modules: umlaut tables, legal-form patterns, dates, person names.

Only helpers whose behaviour is identical across modules live here. The modules keep their own variants
where the difference is deliberate:

* folding: ``idw.fold`` keeps spaces and punctuation (sentence matching), ``foekat._fold`` drops every
  non-alphanumeric character (catalogue keys), ``openalex._fold`` collapses ue/oe/ae and ss (author names
  are spelled both ways), ``patents.normalise_name`` / ``wayback.slugs`` turn the rest into separators;
* legal forms: ``foekat.LEGAL_FORMS`` is case-sensitive about the umlaut and also strips gGmbH, mbH, Co. and
  ``&`` from catalogue names; ``imprint`` and ``classify`` *detect* legal forms instead of stripping them;
* amounts: ``engine.euros`` (statements with currency and Mio/Tsd), ``engine.parse_catalogue`` (catalogue
  sums with dotted thousands), ``foekat.parse_amount`` (first number of a catalogue cell),
  ``classify.parse_money`` (Mio/Mrd with currency) accept different inputs on purpose.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# Lower-case umlauts plus the accents that occur in company names, transliterated to ASCII.
UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
TRANSLIT = str.maketrans({**UMLAUTS, "é": "e", "è": "e", "á": "a", "à": "a"})

_LEGAL_WORDS = r"gmbh\s*&\s*co\.?\s*kg|gmbh|ug|ag|se|kg|ohg|gbr|e\.?\s?v\.?|ltd\.?|inc\.?"
_LEGAL_TAIL = r"|\bi\.\s?gr?\.?(?=\s|$)|\(haftungsbeschr(ä|ae)nkt\)|haftungsbeschr(ä|ae)nkt|in gr(ü|ue)ndung"


def legal_forms(extra: str = "") -> re.Pattern:
    """Case-insensitive pattern of German/English legal forms (GmbH, UG (haftungsbeschränkt), i.G., Ltd ...).

    `extra` adds alternatives to the word list, e.g. ``r"llc|corp\\.?"``.
    """
    words = _LEGAL_WORDS + ("|" + extra if extra else "")
    return re.compile(rf"\b({words})\b{_LEGAL_TAIL}", re.IGNORECASE)


LEGAL_FORMS = legal_forms()

GERMAN_DATE = r"\d{1,2}\.\d{1,2}\.\d{4}"


def german_date(text: str) -> date:
    """'01.09.2024' -> date(2024, 9, 1); raises ValueError for anything else."""
    return datetime.strptime(text, "%d.%m.%Y").date()


def years_before(day: date, years: int) -> date:
    """The same calendar day `years` earlier; 29 February becomes the 28th."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


# --- person names in catalogue units -----------------------------------------------------------------
# The Förderkatalog names the head of a chair or working group inside "Ausführende Stelle"
# ("Universität X, Lehrstuhl Y, Prof. Dr. Erika Musterfrau", "Institut Z AG Vorname Nachname").
# Names are personal data and not needed for the assessment: only the institute designation is kept.
# One function for steps 1 and 2: `strip_persons` (sourcing/mapping.py imports it; context never imports sourcing).

ACADEMIC = re.compile(r"hochschul|universit|institut|akademie|academy|school|college|leibniz|fraunhofer|max-planck|"
                      r"helmholtz|forschung|research|zentrum|center|centre|klinik|charité|wissenschaft", re.I)
_TITLE = (r"(?:Jun\.-Prof\.|Univ\.-Prof\.|apl\.\s?Prof\.|Prof\.|Professorin|Professor|Priv\.-Doz\.|PD|"
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


def _strip_names(text: str) -> str:
    """Remove personal names with academic titles and untitled 'AG <first> <last>' heads, keep the
    institute/chair designation. A field that would become empty is returned unchanged (see `strip_persons`).

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


_PROBE = "Institut"     # appended segment: if only it survives, the field held nothing but a person


def strip_persons(text: str) -> str:
    """Remove titled person names and untitled 'AG <first> <last>' heads, keep the institute designation.

    'Universität X, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau'
    -> 'Universität X, Lehrstuhl für Experimentalphysik VI'; a field that is only a person
    ('Prof. Dr. Erika Musterfrau') becomes '' — callers supply their own fallback ("?", the FKZ, None).
    A heuristic: untitled names outside the 'AG <first> <last>' shape stay (sourcing/FOEKAT.md, known gaps).
    """
    out = _strip_names(text)
    if out and out == text and _strip_names(f"{text}, {_PROBE}") == _PROBE:
        return ""       # `_strip_names` keeps a field that would become empty; a bare name must not survive
    return out
