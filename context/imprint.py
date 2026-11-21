"""Impressum lookup: find the legal-notice page of a German company website and parse it.

`imprint_lookup(website, *, cache, fetch=None)` fetches the homepage, follows footer links whose
path looks like an imprint (impressum, imprint, legal-notice, ...), then tries the usual paths.
The first page with imprint markers is parsed with regexes into `legal_form`, `in_formation`,
`managing_directors`, `register_id`, `contact_email` (generic mailboxes only), `address_city`
and `company_name`. Every value carries an Evidence entry with the matched line(s); the full page
text becomes a SourceSignal(type="impressum"). Nothing is raised, failures land in `errors`.
"""
from __future__ import annotations

import hashlib
import http.client
import logging
import re
from urllib.parse import unquote, urljoin, urlsplit

from context.lookup import SOURCE_IMPRINT, Lookup
from context.web import fetch as _web_fetch, site_key
from models import SourceSignal

logger = logging.getLogger(__name__)
SOURCE = SOURCE_IMPRINT
MAX_REQUESTS = 6
MAX_SIGNAL_CHARS = 8000
COMMON_PATHS = ["/impressum", "/impressum/", "/imprint", "/legal", "/legal-notice", "/de/impressum",
                "/en/imprint", "/impressum.html"]
# Ranking of link candidates: lower is tried first.
LINK_PATTERNS = [
    (0, re.compile(r"impressum", re.I)),
    (1, re.compile(r"imprint", re.I)),
    (2, re.compile(r"legal[-_ ]?notice|rechtliches|site[-_]?notice", re.I)),
    (3, re.compile(r"(?:^|/)legal(?:/|\.|$)", re.I)),
]
GENERIC_MAILBOXES = {
    "info", "kontakt", "contact", "hello", "hallo", "team", "office", "mail", "post", "press", "presse",
    "invest", "founders", "hi", "support", "sales", "service", "jobs", "careers", "karriere", "investors",
    "investor", "legal", "privacy", "datenschutz", "impressum", "admin", "webmaster", "partner", "partners",
}

# --- page recognition -----------------------------------------------------------------------------
STRONG_MARKERS = re.compile(
    r"Angaben\s+gem(?:äß|aess|ass|\.)\s*§\s*5|§\s*5\s+(?:TMG|DDG|ECG)|§\s*18\s+(?:Abs\.\s*2\s+)?MStV"
    r"|\bHR[AB]\s*[:.]?\s*\d|Registergericht|Handelsregister|Vertreten\s+durch|Gesch[äa]ftsf[üu]hr"
    r"|Umsatzsteuer-?\s?(?:ID|Identifikationsnummer)|USt\.?-?\s?Id(?:Nr|-Nr)?\.?|Managing\s+Directors?"
    r"|Commercial\s+Register|Register\s+Court|VAT\s*(?:ID|No)|Represented\s+by|Information\s+(?:pursuant|according)\s+to",
    re.I)
WEAK_HEADINGS = re.compile(r"^(?:Impressum|Imprint|Legal\s+Notice|Legal\s+Disclosure|Site\s+Notice)\s*[:|–-]?\s*$", re.I)

# --- legal forms (ordered: specific before general) ------------------------------------------------
LEGAL_FORMS = [
    ("GmbH & Co. KG", re.compile(r"\b(?:g?GmbH|UG(?:\s*\(haftungsbeschränkt\))?)\s*&\s*Co\.?\s*KGaA\b|\b(?:g?GmbH|UG(?:\s*\(haftungsbeschränkt\))?)\s*&\s*Co\.?\s*KG\b")),
    ("UG (haftungsbeschränkt)", re.compile(r"\bUG\s*\(\s*haftungsbeschr[äa]nkt\s*\)|\bUnternehmergesellschaft(?:\s*\(\s*haftungsbeschr[äa]nkt\s*\))?|\bUG\s+haftungsbeschr[äa]nkt\b|\bUG\b(?=\s*(?:i\.\s?Gr?\.|\(?in\s+Gründung|,|$))")),
    ("gGmbH", re.compile(r"\bgGmbH\b|\bgemeinn[üu]tzige\s+GmbH\b")),
    ("GmbH", re.compile(r"\bGmbH\b|\bGesellschaft\s+mit\s+beschr[äa]nkter\s+Haftung\b|\bmbH\b")),
    ("SE", re.compile(r"(?<=[\w.)]) SE\b(?!\s*&)")),
    ("AG", re.compile(r"(?<=[\w.)]) AG\b(?!\s*&)(?!\s+[A-ZÄÖÜ][\wäöüß-]*\s*,?\s*(?:\(|HR[AB]\b))|\bAktiengesellschaft\b")),
    ("KG", re.compile(r"(?<=[\w.)]) (?:KG|KGaA|OHG|oHG)\b|\bKommanditgesellschaft\b|\boffene\s+Handelsgesellschaft\b")),
    ("GbR", re.compile(r"\bGbR\b|\bGesellschaft\s+b[üu]rgerlichen\s+Rechts\b")),
    ("e.V.", re.compile(r"\be\.\s?V\.(?!\w)|\beingetragener\s+Verein\b")),
    ("Einzelunternehmen", re.compile(r"\bEinzelunternehme[nr]\b|\bEinzelunternehmung\b|\bEinzelkauf(?:mann|frau)\b|\be\.\s?K(?:fm|fr)?\.(?!\w)|\bFreiberufler(?:in)?\b|\bSole\s+(?:proprietor(?:ship)?|trader)\b")),
]
PRIVATE_PERSON = re.compile(
    r"\bPrivatperson\b|\bprivate\s+(?:Person|Website|Webseite|Homepage|Seite)\b|\bprivates?\s+(?:Projekt|Blog)\b"
    r"|\bnicht[-\s]?gewerblich|\bnicht[-\s]?kommerziell|\bkein(?:e)?\s+(?:gewerbliche|kommerzielle)|\bprivate\s+individual\b"
    r"|\bprivately\s+operated\b", re.I)
IN_FORMATION = re.compile(r"\bi\.\s?Gr?\.|\(?\bin\s+Gr[üu]ndung\b\)?|\bin\s+formation\b|\bunder\s+formation\b", re.I)

# --- register, directors, email, address ----------------------------------------------------------
REGISTER = re.compile(r"\b(HRA|HRB|VR|PR|GnR)\s*[:.\-]?\s*(?:Nr\.?\s*)?(\d{1,7})(?!\d)(?:\s*([A-Z]{1,2})(?![\w]))?")
COURT = re.compile(
    r"(?i:Amtsgericht|Registergericht|Register\s+Court|Local\s+Court|District\s+Court|Handelsregister\s+des\s+Amtsgerichts"
    r"|Handelsregister|Commercial\s+Register(?:\s+of\s+the)?)\s*(?i:of\s+|:\s*|-\s*|\s)?"
    r"(?i:(?:District|Local|Register)\s+Court\s+(?:of\s+)?|Amtsgericht\s+|AG\s+)?"
    r"([A-ZÄÖÜ][\wäöüß.\-]*(?:\s*\([\wäöüß.\- ]+\)|(?:\s+(?:am|an|im|in|der|bei)\s+[A-ZÄÖÜ][\wäöüß.\-]*)|\s+[A-ZÄÖÜ][\wäöüß.\-]*)?)",
    re.U)
COURT_STOPWORDS = {"HRB", "HRA", "VR", "Nr", "No", "Number", "Registernummer", "Handelsregister", "Register", "Registergericht",
                   "Unter", "Nummer", "Eintragung", "Umsatzsteuer", "Sitz", "Steuernummer", "Telefon", "Geschäftsführer", "Court"}
REGISTER_NUMBER = re.compile(r"(?:Handelsregister(?:-|\s)?(?:nummer|Nr\.?)|Register(?:-|\s)?(?:nummer|Nr\.?|number|no\.?)|Commercial\s+register\s+(?:number|no\.?))\s*[:.]?\s*(\d{3,7})(?:\s*([A-Z]{1,2}))?(?![\w])", re.I)
HRA_FORMS = {"KG", "GmbH & Co. KG", "Einzelunternehmen"}
DIRECTOR_LABEL = re.compile(
    r"(?:^|[\s(\-/])(?P<label>Gesch[äa]ftsf[üu]hrer(?:in|innen|:in(?:nen)?|\*in(?:nen)?|/-in|/in|/innen|\(in\))?|Gesch[äa]ftsf[üu]hrung"
    r"|Gesch[äa]ftsf[üu]hrende[rn]?\s+Gesellschafter(?:in(?:nen)?)?|Gesch[äa]ftsleitung|Vertreten\s+durch|Vertretungsberechtigt(?:e[rn]?)?(?:\s+Gesch[äa]ftsf[üu]hrer(?:in)?)?"
    r"|Vorstand(?:svorsitzende[rn]?)?|Managing\s+Directors?|Represented\s+by|Legal\s+representatives?|Authori[sz]ed\s+representatives?"
    r"|Executive\s+Board|Board\s+of\s+Directors|Directors?|CEO)\s*(?:\(.*?\))?\s*[:\-–]?\s*(?P<rest>.*)$", re.I)
DIRECTOR_PREFIX = re.compile(
    r"^(?:(?:die|den|der|das|the|unsere|unseren|ihre|ihren|by|durch|sind|ist|is|are)\s+)*"
    r"(?:(?:Gesch[äa]ftsf[üu]hrer(?:in|innen)?|Gesch[äa]ftsf[üu]hrung|Gesch[äa]ftsf[üu]hrende[rn]?\s+Gesellschafter(?:in)?|Managing\s+Directors?|CEO|Vorstand|Vorst[äa]nde|Directors?|Gesellschafter)\s*[:\-–]?\s*)?"
    r"(?:(?:die|den|der|the|unsere|unseren|sind|ist|is|are)\s+)*", re.I)
TITLES = re.compile(
    r"\b(?:Prof\.?|Professor(?:in)?|Dr\.\s*(?:med\.|rer\.\s*nat\.|rer\.\s*pol\.|phil\.|jur\.|h\.\s?c\.|oec\.|iur\.)(?:\s*habil\.)?|Dr\.?(?:-Ing\.?)?|habil\.|Dipl\.?-?\s?(?:Ing\.?|Inf\.?|Kfm\.?|Kffr\.?|Phys\.?|Chem\.?|Biol\.?|Wirt\.?-?Ing\.?|Math\.?|Betriebsw\.?|Volksw\.?|Psych\.?|Päd\.?)(?:\s*\(FH\))?"
    r"|M\.\s?Sc\.?|B\.\s?Sc\.?|M\.\s?A\.?|B\.\s?A\.?|M\.\s?Eng\.?|B\.\s?Eng\.?|MBA|Ph\.?D\.?|PhD|LL\.\s?M\.?|Mag\.?|Ing\.?|Herr(?:n)?|Frau|Mr\.?|Mrs\.?|Ms\.?|Dott\.?|Dipl\.-Kaufmann|Dipl\.-Kauffrau)",
    re.I)
NAME_PARTICLES = {"von", "van", "de", "da", "del", "della", "di", "du", "zu", "zur", "zum", "der", "den", "la", "le", "af", "ten", "ter", "y", "el", "al", "bin", "ibn", "vom"}
ROLE_WORDS = re.compile(
    r"\b(?:CEO|CTO|CFO|COO|CSO|CMO|CPO|CIO|Vorsitzende[rn]?|Sprecher(?:in)?|Chairman|Chairwoman|Founder|Co-?Founder|Gr[üu]nder(?:in)?|Mitgr[üu]nder(?:in)?"
    r"|Gesch[äa]ftsf[üu]hrer(?:in)?|Managing\s+Directors?|Directors?|Vorstand|Prokurist(?:in)?|stellv\.?|stellvertretende[rn]?|Partner|Gesellschafter(?:in)?)\b", re.I)
ADDRESS_WORD = re.compile(r"(?:stra(?:ß|ss)e|str\.|weg|platz|allee|gasse|ring|damm|ufer|chaussee)$|^(?:Telefon|Tel|Fon|Phone|Fax|E-?Mail|Mail|Web|Internet|Registergericht|Amtsgericht|Handelsregister|USt|UID|Sitz|Postfach|c/o)\b", re.I)
EMAIL = re.compile(r"([A-Za-z0-9._%+\-]+)\s*(?:@|\(at\)|\[at\]|\{at\}|\s\(?ät\)?\s|\sat\s)\s*([A-Za-z0-9\-]+(?:\s*(?:\.|\(dot\)|\[dot\])\s*[A-Za-z0-9\-]+)+)", re.I)
POSTAL = re.compile(
    r"(?<!\d)(?:D\s?-\s?)?(\d{5})\s+((?:Bad|Sankt|St\.|Neu|Alt|Ober|Unter|Gro[ßs]|Klein|Hohen|Königs)\s+)?([A-ZÄÖÜ][\wäöüß]+(?:-[A-ZÄÖÜa-zäöü][\wäöüß]+)*)"
    r"(\s+(?:am|an\s+der|im|in\s+der|bei|ob\s+der|a\.\s?M\.)\s+[A-ZÄÖÜ][\wäöüß]+|\s*\((?:Saale|Westf\.?|Oder|Spree|Havel|Weser|Main|Donau|Rhein|Oldb\.?|Holst\.?)\))?")
CITY_STOPWORDS = {"Deutschland", "Germany", "Tel", "Telefon", "Fax", "Mail", "Email", "Phone", "Web", "Mobil", "Handelsregister"}


# ---------------------------------------------------------------------------------------------------
def imprint_lookup(website: str, *, cache, fetch=None) -> Lookup:
    """Locate and parse the imprint of `website`. Never raises; see module docstring."""
    result = Lookup()
    if fetch is None:
        def fetch(url, site):   # the page cache (hits and misses) lives in context.web
            return _web_fetch(url, site, cache=cache)
    try:
        website = _normalise(website)
        site = site_key(website)
        if not site:
            result.errors.append("impressum: ungültige Website")
            return result
        key = "imprint:" + hashlib.sha1(website.encode("utf-8")).hexdigest()
        hit = cache.get(key) if cache is not None else None
        if hit and hit.get("url") and hit.get("text"):
            imprint_url, text = hit["url"], hit["text"]
        elif hit and hit.get("error"):
            result.errors.append("impressum: " + hit["error"])     # memoised miss, no new requests
            return result
        else:
            imprint_url, text = _find_imprint(website, site, fetch)
            if cache is not None:
                cache.set(key, {"url": imprint_url, "text": text} if imprint_url else {"error": "nicht gefunden"})
        if not imprint_url:
            result.errors.append("impressum: nicht gefunden")
            return result
        _parse_into(result, imprint_url, text)
    except Exception as exc:  # noqa: BLE001 - contract: never raise
        logger.info("Impressum lookup failed for %s: %s", website, type(exc).__name__)
        result.errors.append("impressum: " + type(exc).__name__)
    return result


def _normalise(website: str) -> str:
    website = (website or "").strip()
    if website and "://" not in website:
        website = "https://" + website
    parts = urlsplit(website)
    return parts._replace(path=parts.path or "/", query="", fragment="").geturl()


def _find_imprint(website: str, site: str, fetch):
    """Return (url, text) of the first page with imprint markers, or (None, None)."""
    requests = 0
    tried = set()
    homepage_url = website

    def get(url):
        nonlocal requests
        clean = urlsplit(url)._replace(fragment="").geturl()
        if clean in tried or requests >= MAX_REQUESTS:
            return None, None
        tried.add(clean)
        requests += 1
        try:
            final_url, page = fetch(clean, site)
        except (OSError, UnicodeError, ValueError, LookupError, http.client.HTTPException) as exc:
            logger.info("Imprint page unavailable %s (%s)", clean, type(exc).__name__)
            return None, None
        tried.add(urlsplit(final_url)._replace(fragment="").geturl())
        return final_url, page

    final_url, page = get(website)
    candidates = []
    if page is not None:
        homepage_url = final_url
        text = "\n".join(page.lines)
        if STRONG_MARKERS.search(text):
            return final_url, text
        seen = {}
        for href in page.links:
            try:
                link = urljoin(final_url, href.strip())
                parsed = urlsplit(link)
            except ValueError:
                continue
            if site_key(link) != site or parsed.scheme not in {"http", "https"}:
                continue
            target = unquote(parsed.path + ("?" + parsed.query if parsed.query else ""))
            rank = next((rank for rank, pattern in LINK_PATTERNS if pattern.search(target)), None)
            if rank is None or "datenschutz" in target.lower() or "privacy" in target.lower():
                continue
            clean = parsed._replace(fragment="").geturl()
            if clean not in seen or seen[clean] > rank:
                seen[clean] = rank
        candidates = sorted(seen, key=lambda link: (seen[link], len(link)))
    base = urlsplit(homepage_url)._replace(path="/", query="", fragment="").geturl()
    for path in COMMON_PATHS:
        candidates.append(urljoin(base, path))
    for url in candidates:
        if requests >= MAX_REQUESTS:
            break
        final_url, page = get(url)
        if page is None:
            continue
        text = "\n".join(page.lines)
        if _looks_like_imprint(text):
            return final_url, text
    return None, None


def _looks_like_imprint(text: str) -> bool:
    if STRONG_MARKERS.search(text):
        return True
    heading = any(WEAK_HEADINGS.match(line) for line in text.split("\n")[:80])
    form = any(pattern.search(text) for _, pattern in LEGAL_FORMS)
    return heading or form


# --- parsing ---------------------------------------------------------------------------------------
def parse_imprint(text: str) -> dict:
    """Parse imprint text into {field: (value, finding)}; pure function used by `_parse_into`."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    out = {}
    form = _legal_form(lines)
    if form:
        name, label, line, idx = form
        out["legal_form"] = (label, line)
        if name:
            out["company_name"] = (name, line)
    register = _register(lines, out["legal_form"][0] if form else None)
    if register:
        out["register_id"] = register
    if form and label != "keine":
        hit = next((l for l in lines[idx:idx + 2] if IN_FORMATION.search(l)), None)
        if hit:
            out["in_formation"] = (True, hit)
        elif register:
            out["in_formation"] = (False, register[1])
    directors = _directors(lines)
    if directors:
        out["managing_directors"] = directors
    email = _generic_email(lines)
    if email:
        out["contact_email"] = email
    city = _city(lines)
    if city:
        out["address_city"] = city
    return out


def _legal_form(lines):
    """Return (company_name, label, line, index) for the first line naming a legal form."""
    best = None
    for idx, line in enumerate(lines):
        if REGISTER.search(line) and "HRB" in line and not any(p.search(line) for n, p in LEGAL_FORMS if n != "AG"):
            continue  # register lines ("AG Charlottenburg HRB ...") are not company-name lines
        for label, pattern in LEGAL_FORMS:
            match = pattern.search(line)
            if not match:
                continue
            if label == "AG" and re.search(r"\b(?:Amtsgericht|Registergericht|HR[AB])\b", line) and not re.search(r"\w\s+AG\s*(?:,|$|i\.\s?G)", line):
                continue
            name = _company_name(line, match)
            if name:  # a short "Name + Rechtsform" line beats a prose mention ("...erstellt von der X AG")
                return name, label, line, idx
            if best is None:
                best = (None, label, line, idx)
            break
    if best:
        return best
    for idx, line in enumerate(lines):
        if PRIVATE_PERSON.search(line):
            return None, "keine", line, idx
    return None


def _company_name(line, match):
    head = line[:match.start()].strip(" ,;:-–|")
    head = re.sub(r"^(?:Firma|Firmenname|Name|Unternehmen|Company|Anbieter|Betreiber|Herausgeber|Dienstanbieter|Diensteanbieter|Verantwortlich(?:er)?|Provider|Operator)\s*[:\-–]\s*", "", head, flags=re.I)
    head = re.sub(r"^(?:die|der|das|the|Impressum|Imprint|Legal\s+Notice)\s+", "", head, flags=re.I)
    if not head or len(head) > 80 or len(head.split()) > 8 or "@" in head or re.search(r"\d{5}", head):
        return None
    if not re.match(r"^[\wäöüÄÖÜß&.'’\-\s()+/!:]+$", head, re.U) or not re.search(r"[A-Za-zÄÖÜäöü]", head):
        return None
    if re.search(r"\b(?:ist|sind|eine?|als|wird|der|die|das|von|für|durch|bei|und|oder|is|are|a|an|the|of|for|by|with|operated|betrieben)\b", head, re.I) and len(head.split()) > 3:
        return None
    tail = IN_FORMATION.match(line[match.end():].strip(" ,"))
    return head + " " + match.group(0).strip() + (" " + tail.group(0).strip("() ") if tail else "")


def _register(lines, form=None):
    hits = []
    for idx, line in enumerate(lines):
        match = REGISTER.search(line)
        if match and match.group(1) in {"VR", "PR", "GnR"} and not re.search(r"Register|Verein|Partnerschaft|Genossenschaft", " ".join(lines[max(0, idx - 2):idx + 2]), re.I):
            match = None
        if match:
            hits.append((0, idx, match.group(1) + " " + match.group(2) + (" " + match.group(3) if match.group(3) else "")))
            break
        plain = REGISTER_NUMBER.search(line)
        if plain and not hits:
            kind = "HRA" if form in HRA_FORMS else "HRB" if form and form not in {"e.V.", "GbR", "keine"} else "Nr."
            hits.append((1, idx, kind + " " + plain.group(1) + (" " + plain.group(2) if plain.group(2) else "")))
    if not hits:
        return None
    for _, idx, number in sorted(hits):
        line = lines[idx]
        court, court_line = None, None
        window = [line] + lines[max(0, idx - 3):idx] + lines[idx + 1:idx + 4]
        for candidate in window:
            c = COURT.search(candidate)
            if c and c.group(1).split()[0].rstrip(".,:") not in COURT_STOPWORDS:
                court = c.group(1).strip(" .,:;-")
                court = re.sub(r"\s+(?:HR[AB]|unter|Nr|Nummer)\b.*$|\s*(?:Handelsregister|Registernummer|Register\s*-?\s*[Nn]).*$", "", court)
                court_line = candidate
                break
        value = number + (", Amtsgericht " + court if court else "")
        finding = line if court_line in (None, line) else line + "\n" + court_line
        return value, finding
    return None


# Words that never occur in a person's name: field labels and departments that the label regex picks up
# ("Product Development", "Commercial Register", "VAT ID", live run 21.11.2026).
NON_PERSON_WORDS = {
    "product", "products", "development", "commercial", "register", "registration", "vat", "id", "ust", "ust-id",
    "tax", "steuernummer", "number", "nummer", "management", "board", "office", "team", "sales", "marketing",
    "support", "company", "gesellschaft", "registergericht", "handelsregister", "amtsgericht", "court", "contact",
    "kontakt", "information", "informationen", "angaben", "responsible", "verantwortlich", "content", "inhalt",
    "university", "universität", "institut", "institute", "department", "abteilung",
}
# Representatives of a public body (university imprint: "legally represented by the Rector ..."): not a company's
# managing director, the site is not a company site in that respect.
PUBLIC_REPRESENTATIVE = re.compile(r"\b(?:Rector|Rektor(?:in)?|Pr[äa]sident(?:in)?|President|Kanzler(?:in)?|Chancellor|Dekan(?:in)?|Dean)\b", re.I)


def _directors(lines):
    names, findings = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = DIRECTOR_LABEL.search(line)
        i += 1
        if not match:
            continue
        if PUBLIC_REPRESENTATIVE.search(line):
            continue
        label = match.group("label").lower()
        if label.startswith("director") and not re.search(r"^(?:Managing\s+)?Directors?\s*[:\-–]", line, re.I):
            continue  # "director" inside prose (e.g. "Art Director")
        rest = DIRECTOR_PREFIX.sub("", match.group("rest").strip())
        if label == "ceo" and not match.group("rest").strip():
            continue
        if ":" in rest and not _split_names(rest.split(":", 1)[0]):
            rest = rest.rsplit(":", 1)[1]  # "authorized to represent the company: Dr. X"
        if label.startswith("vertreten") and re.search(r"\b(?:Gesellschaft|GmbH|Komplementär|persönlich haftende)", rest, re.I) and not _split_names(rest):
            continue
        found = _split_names(rest)
        used = [line]
        if not found and not rest.strip(" :-–"):
            # Names on the following lines until something that is not a name.
            while i < len(lines) and len(found) < 6:
                nxt = lines[i]
                if DIRECTOR_LABEL.search(nxt):
                    break  # handled by the outer loop with its own label
                part = _split_names(nxt)
                if not part or re.search(r"\d|@|:", nxt):
                    break
                found.extend(part)
                used.append(nxt)
                i += 1
        for name in found:
            if name not in names:
                names.append(name)
        if found:
            findings.extend(used)
        if len(names) >= 6:
            break
    if not names:
        return None
    return names[:8], "\n".join(dict.fromkeys(findings))


def _split_names(text):
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\b(?:sowie|und|and|&|/|;|\|)\b|&|/|;|\|", ",", text)
    out = []
    for part in text.split(","):
        part = TITLES.sub(" ", part)
        part = ROLE_WORDS.sub(" ", part)
        part = re.sub(r"\b(?:die|der|den|the|unsere|unseren|sind|ist|is|are|Herr|Frau|Mr|Mrs|Ms)\b\.?", " ", part, flags=re.I)
        tokens = part.replace("·", " ").split()
        for n, token in enumerate(tokens):  # cut at address or label tokens glued to the name line
            if re.search(r"\d|@|§", token) or ADDRESS_WORD.search(token):
                tokens = tokens[:n]
                break
        part = " ".join(tokens).strip(" .,:;-–")
        tokens = part.split()
        if not 2 <= len(tokens) <= 5:
            continue
        if any(t.lower().strip(".:") in NON_PERSON_WORDS for t in tokens):
            continue
        caps = [t for t in tokens if t.lower() not in NAME_PARTICLES]
        if len(caps) < 2 or not all(re.match(r"^[A-ZÄÖÜÀ-Þ][\wäöüßÀ-ÿ'’\-.]*$", t) for t in caps):
            continue
        if any(t.isupper() and len(t) > 3 for t in caps) and not all(t.isupper() for t in caps):
            continue
        out.append(part)
    return out


def _generic_email(lines):
    for line in lines:
        for match in EMAIL.finditer(line):
            local = match.group(1).lower().rstrip(".")
            domain = re.sub(r"\s*(?:\(dot\)|\[dot\]|\.)\s*", ".", match.group(2)).lower()
            if local in GENERIC_MAILBOXES:
                return local + "@" + domain, line
    return None


def _city(lines):
    for line in lines:
        match = POSTAL.search(line)
        if not match:
            continue
        if match.group(3) in CITY_STOPWORDS:
            continue
        city = (match.group(2) or "") + match.group(3) + (match.group(4) or "")
        return " ".join(city.split()), line
    return None


def _parse_into(result: Lookup, imprint_url: str, text: str) -> None:
    parsed = parse_imprint(text)
    result.add("imprint_url", imprint_url, url=imprint_url, finding=text[:200] or imprint_url, source=SOURCE)
    for name, (value, finding) in parsed.items():
        result.add(name, value, url=imprint_url, finding=finding, source=SOURCE)
    if text.strip():
        result.signals.append(SourceSignal(source=SOURCE, type="impressum", url=imprint_url,
                                           evidence=text[:MAX_SIGNAL_CHARS]))
