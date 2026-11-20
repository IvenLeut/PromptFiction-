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
# One implementation for steps 1 and 2: the rules live in sourcing/mapping.py `strip_persons` (imported lazily,
# because sourcing imports context.foekat); this wrapper adds the step-2 rule for a field that is only a person.
_PROBE = "Institut"     # appended segment: if only it survives, the field held nothing but a person


def strip_persons(text: str) -> str:
    """Remove titled person names and untitled 'AG <first> <last>' heads, keep the institute designation.

    'Universität X, Lehrstuhl für Experimentalphysik VI, Prof. Dr. Erika Musterfrau'
    -> 'Universität X, Lehrstuhl für Experimentalphysik VI'; 'Prof. Dr. Erika Musterfrau' -> ''.
    """
    from sourcing.mapping import strip_persons as strip_step1
    out = strip_step1(text)
    if out and out == text and strip_step1(f"{text}, {_PROBE}") == _PROBE:
        return ""       # step 1 keeps a field that would become empty; here a bare name must not survive
    return out
