"""Team composition (loop round 1): who is in the team, which role, tech or business background.

Two sources, in this order (`team_lookup`):

1. **Texts already collected, no request:** press/idw articles, project pages, website team/about text. Patterns:
   picture captions "Das <Firma>-Team (v.l.n.r. A, B und C)", lists "Gründerteam: A, B und C" / "founders A and B",
   and role sentences "<Name>, Mitgründer und …", "<Name> (CTO)", "<Name>, who … is taking over as CEO".
2. **Brave API search results (snippets only, never a linkedin.com page fetch):**
   * `site:linkedin.com/in "<Firma>"` (plus the place for short names): a profile title "Name - <Firma> | LinkedIn"
     names the person's current company. A person counts only if the title company is the lead **and** the person
     is a known name (Impressum) or carries a founder role in the headline (Founder, Co-Founder, Gründer, CEO, CTO …).
     Without known names, people whose current company is the lead become "Teammitglied". Everyone else in the
     results only liked/shared a company post and is dropped. Unknown persons additionally need a confirmation
     (place, Germany, a German university in "Education:", the institute, EXIST or the website domain): a US firm of
     the same name or people with the surname "Secara" are rejected.
   * `"<Firma>" (Gründer OR Gründerteam OR founders …) <Institut>` (only when no founder is known yet): snippets are
     read with the text patterns of step 1, origin "Presse".
   * `site:linkedin.com/in "<known name>"` for one Impressum director not found yet.

Roles follow the format agreed with `scorer`: "<Rolle> (<Herkunft>)" with Herkunft Impressum | LinkedIn | Presse |
Website, "Teammitglied (<Herkunft>)" for non-founders, "Alleingründer (<Herkunft>)" only if a source says so.
Background ("tech" | "business" | "beides") only from role or education words (`background_from`); CEO alone -> None.
Stored per person: name, role, background, one university, profile/press URL. Never stored: place, contacts,
e-mail, phone, photo, connection counts, post texts. `prior_experience` is not set.

Limits: at most `MAX_QUERIES` searches per lead, `MAX_RUN_REQUESTS` new API requests per process (round budget),
everything through the cache (`team:v3:` per lead, `context.http` per request). Nothing is raised.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import quote_plus, urlsplit

from context import http as _http
from context import website_match as wm
from context.lookup import Lookup
from models import Evidence, FounderProfile

CACHE_VERSION = "team:v3:"
MAX_QUERIES = 3            # searches per lead
MAX_RUN_REQUESTS = 170     # new Brave requests per process (round budget 180)
MAX_PEOPLE = 8             # persons kept per lead
STATS = {"requests": 0, "cached": 0, "skipped_budget": 0}
SOURCE = "Teamsuche"
ORIGINS = ("Impressum", "LinkedIn", "Presse", "Website")

TITLE_WORDS = r"(?:Prof\.|Professor(?:in)?|Dr\.(?:-Ing\.|\s?rer\.\s?nat\.|\s?med\.)?|Dipl\.-Ing\.|M\.\s?Sc\.|B\.\s?Sc\.|PhD|Ph\.D\.|MBA)"
NAME_TOKEN = r"[A-ZÄÖÜ][a-zäöüßéèáàçñ]+(?:-[A-ZÄÖÜ][a-zäöüßéèáàçñ]+)?(?![A-Za-zÄÖÜäöüß])"
PARTICLE = r"(?:von|van|de|der|den|zu|da|del|di|al|el|bin)"
PERSON = rf"(?:{TITLE_WORDS}\s*)*({NAME_TOKEN}(?:\s+(?:{PARTICLE}\s+)?{NAME_TOKEN}){{1,2}})"
PERSON_RE = re.compile(PERSON)
FOUNDER_ROLE = re.compile(r"\b(?:Co-?Founder|Cofounder|Founder|Gründer(?:in)?|Mitgründer(?:in)?|Mitbegründer(?:in)?|Gründungsmitglied|"
                          r"CEO|CTO|COO|CFO|CBO|CSO|Geschäftsführer(?:in)?|Managing Director)\b", re.IGNORECASE)
ROLE_TOKEN = re.compile(r"\b(?:Co-?Founder|Cofounder|Founder|Gründer(?:in)?|Mitgründer(?:in)?|Mitbegründer(?:in)?|CEO|CTO|COO|CFO|CBO|"
                        r"CSO|Geschäftsführer(?:in)?|Managing Director|Head of [A-Z][\w&-]+(?: [A-Z][\w&-]+)?|"
                        r"Chief [A-Z]\w+ Officer)\b")
SOLO = re.compile(r"\b(?:Alleingründer(?:in)?|Solo-?Gründer(?:in)?|solo founder|sole founder|einzige[rn]? Gründer(?:in)?)\b", re.I)
BUSINESS = re.compile(r"kaufmännisch|kommerziell|commercial|business development|\bCFO\b|\bCOO\b|\bCBO\b|\bsales\b|vertrieb|marketing|"
                      r"\bBWL\b|Betriebswirt|\bMBA\b|\bmanagement\b|economics|Wirtschaftswissenschaft|finance|finanz", re.I)
TECH = re.compile(r"\bCTO\b|engineer|engineering|(?<!unternehmens)(?<!geschäfts)(?<!business )entwicklung|developer|software|robotik|robotics|physi[ck]|chemi|informatik|"
                  r"computer science|mathemati|maschinenbau|mechanical|electrical|elektrotechnik|biolog|biotech|medizin|"
                  r"medicine|materials|werkstoff|Dr\.-Ing\.|Head of (?:Engineering|R&D|Research|Technology|Software|Hardware)", re.I)
BOTH = re.compile(r"Wirtschaftsingenieur|industrial engineering|Wirtschaftsinformatik|business informatics", re.I)
GERMAN_UNI = re.compile(r"Universität|Universitaet|Hochschule|\bTU\b|\bTUM\b|\bRWTH\b|\bKIT\b|\bLMU\b|Fraunhofer|Helmholtz|Leibniz|"
                        r"Max-Planck|Technische Universit|University of (?:Stuttgart|Freiburg|Hamburg|Bremen|Bonn|Cologne|Göttingen)", re.I)
GERMANY = re.compile(r"\b(?:Germany|Deutschland|Bayern|Sachsen|Hessen|Baden-Württemberg|Nordrhein-Westfalen|Niedersachsen|Berlin|"
                     r"Hamburg|Bremen|Brandenburg|Thüringen|Rheinland-Pfalz|Saarland|Schleswig-Holstein|Mecklenburg)\b", re.I)
CAPTION = re.compile(r"\((?:v\.\s?l\.\s?n\.\s?r\.|v\.\s?l\.|f\.\s?l\.\s?t\.\s?r\.|from left(?: to right)?|von links(?: nach rechts)?)[.:,]?\s*([^)]{5,400})\)",
                     re.I)
TEAM_LIST = re.compile(r"(?:Gründerteam|Gründungsteam|Gründer(?:innen)?|founding team|founders|co-founders|Das Team)\s*(?:sind|are|:|–|-)\s*"
                       r"([^.;\n]{5,300})", re.I)
ROLE_WORD_IN_NAME = re.compile(r"gründer|founder|geschäftsführ|leiter|manager|director|officer|professor|team|institut|"
                               r"universit|gmbh", re.I)
# Contact-data brokers: never a source (round-1 plan: no third-party people scrapers), even as a search snippet.
BROKER_HOSTS = re.compile(r"(?:^|\.)(?:rocketreach|zoominfo|apollo|lusha|signalhire|contactout|leadiq|kaspr|seamless|"
                          r"cognism|adapt|uplead|yasni|dasoertliche|dastelefonbuch|personensuche)\.[a-z.]+$", re.I)
MIN_NAME_CHARS = 4         # "KM", "P2P", "TSS": too ambiguous for a person search
NOT_A_NAME = {"legal", "notice", "imprint", "impressum", "privacy", "contact", "kontakt", "cookie", "terms", "policy",
              "home", "about", "news", "career", "careers", "jobs", "based", "on", "the", "of", "and", "und", "der", "die", "das", "team", "gmbh", "university", "universität", "institut",
              "institute", "german", "bundestag", "european", "union", "ministry", "federal", "start", "project", "projekt"}


@dataclass
class Person:
    name: str
    role: str                       # "<Rolle> (<Herkunft>)"
    url: str
    background: str | None = None
    institution: str | None = None
    confidence: float = 0.7
    finding: str = ""


# --- name helpers ---------------------------------------------------------------------------------

def clean_person(text: str) -> str | None:
    """'Dr.-Ing. Mohamad Bdiwi' -> 'Mohamad Bdiwi'; None for anything that is not a 2-3 word person name."""
    text = re.sub(r"[（(][^)）]*[)）]", " ", text or "")
    text = re.sub(TITLE_WORDS, " ", text)
    text = " ".join(text.replace("·", " ").split()).strip(" ,.;:-–")
    match = re.fullmatch(rf"{NAME_TOKEN}(?:\s+(?:{PARTICLE}\s+)?{NAME_TOKEN}){{1,2}}", text)
    if not match or any(t.casefold() in NOT_A_NAME for t in text.split()) or ROLE_WORD_IN_NAME.search(text):
        return None
    return text


def name_key(name: str) -> str:
    """Folded first + last token: 'Dr. Felix Hoffmann' and 'Felix Hoffmann' share a key."""
    tokens = wm.fold(clean_person(name) or name).split()
    return "%s %s" % (tokens[0], tokens[-1]) if len(tokens) >= 2 else " ".join(tokens)


def background_from(text: str) -> str | None:
    """'tech' / 'business' / 'beides' from role and education words; CEO alone says nothing (None)."""
    if BOTH.search(text or ""):
        return "beides"
    business, tech = bool(BUSINESS.search(text or "")), bool(TECH.search(text or ""))
    return "beides" if business and tech else "business" if business else "tech" if tech else None


def role_text(text: str) -> str | None:
    tokens = list(dict.fromkeys(m[0] for m in ROLE_TOKEN.finditer(text or "")))
    return " & ".join(tokens[:3]) if tokens else None


# --- step 1: texts without a request --------------------------------------------------------------

OTHER_ORG = re.compile(r"\b(?:GmbH|AG|SE|e\.\s?V\.|Inc\.?|Ltd\.?|Institut\w*|Universit\w*|Hochschule|Fraunhofer|Helmholtz|"
                       r"Leibniz|Max-Planck|Stiftung|Bank|Ministeri\w*)\b")
ABBREVIATION = re.compile(r"(?:\b(?:Dr|Prof|Dipl|Ing|bzw|ca|Nr|vgl|St|Mr|Mrs|Ms|Jr|Inc|e\.V|z\.B|u\.a|v\.l\.n\.r|v\.l|f\.l\.t\.r|"
                          r"[A-Z])\.)$")


def _dash_list(company: str) -> re.Pattern:
    names = "|".join(re.escape(n) for n in dict.fromkeys([company, wm.spaced_name(company)]))
    return re.compile(rf"(?:Die|Das|The)\s+(?:{names})(?:[- ]Team)?\s*[–—]\s*(.{{5,300}}?)\s*[–—]\s", re.IGNORECASE)


def _role_of_other_company(tail: str, name_re) -> bool:
    """True if the role word is directly followed by another proper name ("Gründer ReduCO2", "CEO der Transfer GmbH")."""
    m = ROLE_TOKEN.search(tail)
    if not m:
        return False
    rest = tail[m.end():]
    after = re.match(r"\s*(?:(?:von|der|des|bei|at|of|from)\s+)?([A-ZÄÖÜ][\w-]*)", rest)
    return bool(after) and not name_re.search(wm.fold(rest[:60]))


def sentences(text: str) -> list[str]:
    """Sentences of a text; no split after titles and abbreviations ('Dr. Peter', 'v.l.n.r. Dr. …')."""
    out = []
    for line in (text or "").splitlines():
        buf = ""
        for piece in re.split(r"(?<=[.!?])\s+", line):
            buf = (buf + " " + piece).strip() if buf else piece
            if not ABBREVIATION.search(buf):
                out.append(buf)
                buf = ""
        if buf:
            out.append(buf)
    return out


def _split_people(text: str) -> list[str]:
    parts = re.split(r",\s*|\s+(?:und|and|sowie|&)\s+", text)
    return [n for n in (clean_person(p) for p in parts) if n]


def people_from_text(text: str, url: str, company: str, origin: str) -> list[Person]:
    """Team captions, team lists and role sentences that name the company (see module docstring)."""
    out: list[Person] = []
    name_re = wm.name_regex(company)
    if not text or name_re is None:
        return out
    parts = sentences(text)
    # Pass 1: captions and team lists (they define who belongs to the team in this text).
    for sentence in parts:
        folded = wm.fold(sentence)
        about = bool(name_re.search(folded))
        if about or re.search(r"\bteam\b", folded):
            for m in CAPTION.finditer(sentence):
                if about or "team" in folded[:m.start() + 1]:
                    for person in _split_people(m[1]):
                        out.append(Person(person, "Teammitglied (%s)" % origin, url, confidence=0.8, finding=sentence[:400]))
        if about:
            for m in TEAM_LIST.finditer(sentence):
                for person in _split_people(m[1]):
                    out.append(Person(person, "Gründer (%s)" % origin, url, confidence=0.8, finding=sentence[:400]))
        # "Die Botfellows – Dr.-Ing. A (CEO), B, C und D – sind ... ein Team": dash-enclosed team list after the name.
        for m in _dash_list(company).finditer(sentence):
            for raw in re.split(r",\s*|\s+(?:und|and|sowie|&)\s+", m[1]):
                person = clean_person(re.sub(r"\([^)]*\)", " ", raw))
                if person:
                    inner = re.search(r"\(([^)]*)\)", raw)
                    role = role_text(inner[1]) if inner else None
                    out.append(Person(person, "%s (%s)" % (role or "Teammitglied", origin), url,
                                      background=background_from(inner[1]) if inner else None, confidence=0.8,
                                      finding=sentence[:400]))
    members = {name_key(p.name) for p in out}
    # Pass 2: role sentences, in sentences naming the company or about a person of the team list.
    for sentence in parts:
        about = bool(name_re.search(wm.fold(sentence)))
        for m in PERSON_RE.finditer(sentence):
            person = clean_person(m[0])
            if not person or not (about or name_key(person) in members):
                continue
            tail = sentence[m.end():m.end() + 140]
            nxt = next((n for n in PERSON_RE.finditer(tail) if clean_person(n[0])), None)
            tail = tail[:nxt.start()] if nxt else tail                                # stop at the next person
            lead_named = bool(name_re.search(wm.fold(tail)))
            if not lead_named and OTHER_ORG.search(tail):
                continue                                   # "Dr. B. Fremd, CEO der Transfer GmbH": another organisation
            if _role_of_other_company(tail, name_re):
                continue                                   # "Marie Muster, Gründerin Bioexotec": founder of another firm
            solo = SOLO.search(tail[:80])
            if ((role := role_text(tail)) or solo) and re.match(r"\s*(?:,|\(|–|-|ist|is|who|der|die|als|as)", tail):
                label = "Alleingründer" if solo else role
                out.append(Person(person, "%s (%s)" % (label, origin), url, background=background_from(tail[:120]),
                                  confidence=0.8, finding=sentence[:400]))
    return out


# --- step 2: search results -----------------------------------------------------------------------

def _linkedin_parts(hit) -> tuple[str | None, str, str, str | None]:
    """(person, title company, headline, education) of a linkedin.com/in hit; headline only for profile-style snippets."""
    title = re.sub(r"\s*\|\s*LinkedIn\s*$", "", hit.title or "")
    parts = re.split(r"\s+[-–]\s+", title, maxsplit=1)
    person = clean_person(parts[0]) if parts else None
    company = parts[1].strip() if len(parts) > 1 else ""
    snippet = hit.snippet or ""
    headline, education = "", None
    if "Experience:" in snippet or "Education:" in snippet or "Berufserfahrung:" in snippet or "Ausbildung:" in snippet:
        headline = re.split(r"\s·\s(?:Experience|Berufserfahrung|Education|Ausbildung|Location|Standort):", snippet)[0]
        if (m := re.search(r"(?:Education|Ausbildung):\s*([^·]+)", snippet)):
            education = m[1].strip()[:120]
    return person, company, headline, education


def _company_is(text: str, company: str) -> bool:
    """The title company is the lead: its words start with the project name ('Botfellows', 'SECARA GmbH')."""
    name_re = wm.name_regex(company)
    return bool(name_re and re.match(r"\s*" + name_re.pattern, wm.fold(text)))


def _confirmed(hit, location: str | None, institution: str | None, website: str | None) -> list[str]:
    snippet = hit.snippet or ""
    loc = re.search(r"(?:Location|Standort):\s*([^·]+)", snippet)
    reasons = []
    place = wm.fold(re.split(r"[\s,(]", location.strip())[0]) if location and location.strip() else ""
    if loc and (GERMANY.search(loc[1]) or (place and place in wm.fold(loc[1]))):
        reasons.append("Ort")
    if (m := re.search(r"(?:Education|Ausbildung):\s*([^·]+)", snippet)) and GERMAN_UNI.search(m[1]):
        reasons.append("deutsche Hochschule")
    if any(wm.contains(wm.fold(snippet), t) for t in wm.institution_terms(institution)):
        reasons.append("Institut")
    if wm.EXIST.search(snippet):
        reasons.append("EXIST")
    if website and wm.site_key(website) in snippet.lower():
        reasons.append("Website-Domain")
    return reasons


def people_from_linkedin(hits, company: str, known: list[str], *, location=None, institution=None, website=None,
                         errors: list | None = None) -> list[Person]:
    known_keys = {name_key(k): k for k in known}
    out: list[Person] = []
    for hit in hits:
        if "linkedin.com/in/" not in hit.url:
            continue
        person, title_company, headline, education = _linkedin_parts(hit)
        if not person or not _company_is(title_company, company):
            continue                                   # liker / reposter / other employer
        role = role_text(headline)
        is_known = name_key(person) in known_keys
        if not is_known:
            reasons = _confirmed(hit, location, institution, website)
            if not reasons:
                if errors is not None:
                    errors.append("team: %s ohne Bezug zum Lead verworfen (möglicher Namensvetter)" % hit.url)
                continue
        if not is_known and not (role and FOUNDER_ROLE.search(role)) and known:
            continue                                   # with known founders, extra non-founders are not taken over
        url = hit.url.split("?")[0]
        label = role if role and FOUNDER_ROLE.search(role) else ("Teammitglied" if not is_known else role or "Teammitglied")
        finding = "LinkedIn-Suchtreffer: %s – %s%s" % (person, title_company, (" · " + headline[:160]) if headline else "")
        out.append(Person(known_keys.get(name_key(person), person) if is_known else person, "%s (LinkedIn)" % label, url,
                          background=background_from(" ".join(filter(None, [headline, education, hit.title]))),
                          institution=education if education and GERMAN_UNI.search(education or "") else education,
                          confidence=0.9 if is_known else 0.8 if role and FOUNDER_ROLE.search(role) else 0.7, finding=finding))
    return out


def people_from_press(hits, company: str) -> list[Person]:
    out = []
    for hit in hits:
        if "linkedin.com" in hit.url or BROKER_HOSTS.search(wm.site_key(hit.url)):
            continue
        out += people_from_text("%s. %s" % (hit.title, hit.snippet), hit.url, company, "Presse")
    return out


# --- merge ----------------------------------------------------------------------------------------

def merge(people: list[Person]) -> list[Person]:
    """One entry per person (name key); roles joined with '; ' (founder roles first), first URL kept."""
    merged: dict[str, Person] = {}
    for p in people:
        key = name_key(p.name)
        if key not in merged:
            merged[key] = Person(**asdict(p))
            continue
        m = merged[key]
        if m.role.startswith("Teammitglied") and not p.role.startswith("Teammitglied"):
            m.url, m.finding = p.url, p.finding         # the source that carries the role is the evidence
        roles = [r for r in (m.role.split("; ") + [p.role]) if r]
        member = [r for r in roles if r.startswith("Teammitglied")]
        others = list(dict.fromkeys(r for r in roles if not r.startswith("Teammitglied")))
        m.role = "; ".join(others or list(dict.fromkeys(member)))
        m.background = m.background or p.background
        m.institution = m.institution or p.institution
        m.confidence = max(m.confidence, p.confidence)
    return list(merged.values())[:MAX_PEOPLE]


# --- entry point ----------------------------------------------------------------------------------

def team_lookup(name: str, *, website: str | None = None, location: str | None = None, institution: str | None = None,
                known_names=(), texts=(), cache=None, search=None) -> tuple[list[FounderProfile], Lookup]:
    """Team members of a lead as FounderProfiles plus evidence; see module docstring. Never raises.

    `texts`: (text, url, origin) of already collected pages (idw, project page, website). `known_names`: Impressum
    directors / step-1 founders (their profiles are enriched by the caller, not duplicated).
    """
    lookup = Lookup()
    company = wm.clean_name(name)
    known = [k for k in known_names if k]
    people: list[Person] = []
    for text, url, origin in texts:
        people += people_from_text(text, url, company, origin)
    key = CACHE_VERSION + hashlib.sha1(repr((company, website, location, institution, tuple(sorted(known)))).encode()).hexdigest()
    live = search is None
    found = None
    if live and cache is not None:
        found = cache.get(key)
    if isinstance(found, dict) and "people" in found:
        searched = [Person(**p) for p in found["people"]]
        lookup.errors.extend(found.get("errors", []))
    else:
        searched, complete = _search(company, known, people, location=location, institution=institution, website=website,
                                     cache=cache, search=search, errors=lookup.errors)
        if live and cache is not None and complete:
            cache.set(key, {"people": [asdict(p) for p in searched], "errors": list(lookup.errors)})
    people = merge(people + searched)
    profiles = []
    for p in people:
        profiles.append(FounderProfile(name=p.name, role=p.role, background=p.background, institution=p.institution,
                                       source_url=p.url, match_confidence=p.confidence))
        lookup.evidence.append(Evidence(field="founder_profiles", url=p.url, source=SOURCE,
                                        finding="%s: %s. %s" % (p.name, p.role, p.finding)[:1000]))
    return profiles, lookup


def _search(company, known, from_texts, *, location, institution, website, cache, search, errors) -> tuple[list[Person], bool]:
    """1-3 searches (LinkedIn company, open team search, one known name); -> (persons, complete)."""
    if len(wm.slug(company)) < MIN_NAME_CHARS:
        errors.append("team: Projektname zu kurz für eine Personensuche")
        return [], True
    if search is None:
        key = wm.api_key()
        if not key:
            errors.append("team: kein BRAVE_API_KEY, nur vorhandene Texte ausgewertet")
            return [], False

        def search(q):
            url = wm.SEARCH_ENGINES["brave_api"] % quote_plus(q)
            if cache is not None and cache.get(_http.cache_key(url)) is not None:
                STATS["cached"] += 1
            elif STATS["requests"] >= MAX_RUN_REQUESTS:
                STATS["skipped_budget"] += 1
                return [], ["team: Anfragebudget der Runde erschöpft"]
            else:
                STATS["requests"] += 1
            return wm.web_search(q, cache=cache, engines=("brave_api",), key=key)
    spaced = wm.spaced_name(company)
    place = re.split(r"[\s,(]", location.strip())[0] if location and location.strip() else ""
    short = len(wm.slug(company)) <= 6
    people: list[Person] = []
    complete = True
    queries = 0

    def run(q):
        nonlocal complete, queries
        queries += 1
        try:
            hits, errs = search(q)
        except Exception as exc:  # noqa: BLE001
            hits, errs = [], ["team: Suche %s" % type(exc).__name__]
        if errs and not hits:
            complete = False
            errors.extend(e.replace("website_match:", "team:") for e in errs)
        return hits

    # LinkedIn titles use the company's own spelling ("Botfellows"); "Bot Fellows" finds other people.
    hits = run('site:linkedin.com/in "%s"%s' % (company, (" " + place) if short and place else ""))
    people += people_from_linkedin(hits, company, known, location=location, institution=institution, website=website,
                                   errors=errors)
    founders = [p for p in people + from_texts if FOUNDER_ROLE.search(p.role) or p.role.startswith("Gründer")]
    if not known and not founders and queries < MAX_QUERIES:
        first = re.split(r"\s+-\s+|,", institution or "")[0].strip()
        hits = run('"%s" (Gründer OR Gründerteam OR Mitgründer OR founders OR "Co-Founder") %s' % (spaced, first))
        people += people_from_press(hits, company)
    found = {name_key(p.name) for p in people}
    missing = [k for k in known if name_key(k) not in found]
    if missing and queries < MAX_QUERIES:
        hits = run('site:linkedin.com/in "%s" "%s"' % (missing[0], company))
        people += [p for p in people_from_linkedin(hits, company, known, location=location, institution=institution,
                                                   website=website, errors=errors) if name_key(p.name) in {name_key(missing[0])}]
    return people, complete
