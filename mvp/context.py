"""Small, conservative prose extractor. Every fact keeps its original URL/quote.

The values are screening signals, not independently established product performance.
No label/value formatting, market-size guesses or language model are required.
"""
import re
from datetime import date
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from free_discovery.core import founding_claims, industries, company_key, identity_match
from mvp.contracts import Dossier, Fact, Source
from mvp.web import canonical_host, excerpt, normalized

PATTERNS = {
 'technology': r'\b(?:sensor\w* fusion|machine learning|deep learning|computer vision|syntheti\w* data|synthetische\w* Daten|algorithm\w*|neural\w*|semiconductor\w*|halbleiter\w*|quantum\w*|quanten\w*|photon\w*|robot\w*|API|SaaS|künstliche\w* Intelligenz|AI[- ](?:enabled|driven|powered)|KI[- ](?:basiert\w*|gestützt\w*)|electrolys\w*|elektrolys\w*|carbon\w*|catalys\w*|katalys\w*|biosensor\w*|biomarker\w*|natural fiber composites|naturfaserverstärkt\w*|prepreg\w*|computer[- ]aided|3D[- ](?:mouse|Maus)|WebRTC|Ende[- ]zu[- ]Ende[- ]Verschlüsselung|large language model\w*)\b',
 'product': r'\b(?:our|unsere?\w*)\s+(?:(?:\w+[ -]){0,3})(?:platform|plattform|software|product|produkt|system|technolog|tool|lösung|loesung)\w*\b|\b(?:SaaS|software platform|Software[- ]Plattform|API[- ](?:platform|first)|proprietary|eigenentwickelt\w*|eigene\w* (?:Software|Technologie|Plattform|Produkte))\b',
 'buyer': r'\b(?:banks|fintechs|Banken|Versicher\w*|manufacturers|Hersteller|manufacturing companies|Produktionsunternehmen|Satellitenbetreiber|satellite operators|operators|physicians|Ärzt\w*|Kliniken|clinics|hospitals|Krankenhäuser|Amazon[- ](?:Seller|Händler)|Seller|Vendors|Verkäufer|Händler|Laboratorien|laboratories|researchers|Forscher|industrial companies|Industrieunternehmen|Industriebetriebe|Stadtwerke|Netzbetreiber|Energieversorger|HR[- ](?:teams|Plattformen)|HR platforms|Ingenieure|Architekten|engineers|architects|dentists|Zahnärzt\w*|Dental\w*|airports|Flughäfen|critical infrastructure|KRITIS|commercial vehicles|Nutzfahrzeug\w*|enterprises|Unternehmen|Betriebe|businesses)\b',
 'benefit': r'\b(?:reduce\w*|reduzier\w*|senk\w*|sparen|beschleunig\w*|automatisier\w*|automat\w*|improv\w*|verbesser\w*|simplif\w*|vereinfach\w*|efficien\w*|effizien\w*|schneller|kostengünstig\w*)\b',
 'team': r'\b(?:co[- ]founder|founder|Gründer(?:duo|team|in)?|Gründungsteam|CEO|CTO|Geschäftsführer(?:in)?)\b',
 'validation': r'\b(?:Prototyp\w*|prototype\w*|proof[- ]of[- ](?:concept|principle)|Pilotprojekt\w*|pilot project\w*|pilot customer\w*|Pilotkund\w*|clinical trial\w*|klinische\w* Studie\w*|patent(?:ed|iert|geschützt)|patent granted|erteiltes Patent|paying customers|zahlende\w* Kunden)\b',
 'regulation': r'\b(?:medical device|Medizinprodukt\w*|clinical|klinisch\w*|Zulassung|regulat\w*|BaFin|MDR|defen[cs]e|Verteidigung)\b',
 'late_round': r'\b(?:raised|secured|closed|abgeschlossen|eingesammelt|Finanzierungsrunde)[^.!?\n]{0,70}\bSeries[- ]?[A-D]\b|\bSeries[- ]?[A-D][^.!?\n]{0,70}\b(?:raised|secured|closed|abgeschlossen|eingesammelt)\b',
 'seed_round': r'\b(?:Pre[- ]Seed|Seed)[- ](?:Runde|round|Finanzierung)\b',
 'inactive': r'\bin Liquidation\b|\bi\.\s?L\.\b|\bGeschäftsbetrieb eingestellt\b',
}
PATTERNS['product'] += r'|\b(?:KI|AI)[- ](?:Telefonassistent\w*|Telefonist\w*|Assistent\w*|receptionist\w*|assistant\w*)\b'
PATTERNS['technology'] += r'|\b(?:KI|AI)[- ](?:Telefonassistent\w*|Telefonist\w*|Assistent\w*|receptionist\w*|assistant\w*)\b'
PATTERNS['buyer'] += r'|\b(?:Autohäuser|Werkstätten|Autohaus|car dealerships|dental laboratories|chip manufacturers)\b'
PATTERNS['buyer'] += r'|\b(?:CNC[- ]Drehteilefertiger|Auftragsfertiger|Lohnfertiger|Zerspanungsbetriebe|machine shops|contract manufacturers)\b'
PATTERNS['benefit'] += r'|\b(?:accelerat\w*|faster|lower costs|weight reduction|reduces? energy)\b'
GENERIC_BUYER = re.compile(r'Unternehmen|Betriebe|businesses|enterprises', re.I)

AGENCY = re.compile(r'\b(?:Digitalagentur|Werbeagentur|IT[- ]Consulting|Softwareagentur|Unternehmensberatung|IT[- ]Dienstleister|individuelle Systeme|individuelle Softwareentwicklung|custom software development)\b|\b(?:wir sind|ist eine?|we are|is an?)\b[^.!?\n]{0,65}\b(?:Agentur|agency|consultancy|Beratungshaus)\b', re.I)


def add_fact(dossier, key, value, page, match, basis='rule_extraction'):
    dossier.facts[key] = Fact(value=value, source_url=page['url'], quote=excerpt(page['text'], match.start()), basis=basis)


def extract(dossier: Dossier, pages: list[dict]):
    for page in pages:
        if page['source'].url not in [s.url for s in dossier.sources]:
            dossier.sources.append(page['source'])
    business = [p for p in pages if not re.search(r'impress|imprint|legal|privacy|datenschutz', p['url'], re.I)]
    for key, pattern in PATTERNS.items():
        generic_buyer = None
        for page in pages if key in {'team', 'inactive'} else business:
            for match in re.finditer(pattern, page['text'], re.I):
                before = page['text'][max(0, match.start()-35):match.start()]
                if re.search(r'\b(?:no|not|kein\w*|noch nicht|planned|geplant)\b', before, re.I):
                    continue
                if key == 'buyer' and GENERIC_BUYER.fullmatch(match.group()):
                    if generic_buyer is None:
                        generic_buyer = (match, page)
                    continue
                add_fact(dossier, key, match.group(), page, match)
                break
            else:
                continue
            break
        else:
            if key == 'buyer' and generic_buyer:
                match, page = generic_buyer
                add_fact(dossier, key, match.group(), page, match)
    # Only a clear service-business self-description triggers a review. A genuine
    # product needs to be assessed separately even when services are also offered.
    for page in business:
        match = AGENCY.search(page['text'][:3500])
        if match:
            add_fact(dossier, 'service_business', match.group(0), page, match)
            break
    tech_text = '\n'.join(p['text'] for p in business)
    dossier.sectors = list(industries(tech_text)) or dossier.sectors
    # A human-readable source excerpt, never an invented product summary.
    candidates=[]
    brand=re.sub(r'\bGmbH\b|\bUG\b.*','',dossier.name,flags=re.I).strip()
    for page in business:
        for line in page['text'].splitlines():
            line=line.strip()
            if not 60<=len(line)<=650 or re.search(r'hätte|would have|hätten|dagegen entschieden|cookie|datenschutz|copyright',line,re.I):continue
            technical=bool(re.search(PATTERNS['technology']+'|'+PATTERNS['product'],line,re.I))
            named=brand.casefold() in line.casefold()
            active=bool(re.search(r'entwickel\w*|fertig\w*|produzier\w*|entwickelt|bietet|develop\w*|manufactur\w*|build\w*|enables?|erfasst',line,re.I))
            if technical or (named and active):candidates.append((int(named)+int(active)+int(technical),page,line))
    if candidates:
        _,page,line=max(candidates,key=lambda c:(c[0],-len(c[2])))
        match=re.search(re.escape(line),page['text'])
        value=' '.join(line.split()[:23])+(' …' if len(line.split())>23 else '')
        add_fact(dossier,'description',value,page,match,'company_self_description')
    extract_contact(dossier, pages)
    return dossier


def extract_contact(dossier, pages):
    """Collect public general business inboxes published by the same company."""
    if not dossier.website:
        return
    host = canonical_host(dossier.website)
    allowed = re.compile(r"(?:info|hello|kontakt|contact|hallo|office|team)@[a-z0-9.-]+\.[a-z]{2,63}", re.I)
    ordered = sorted(pages, key=lambda page: not bool(re.search(r"impress|imprint|contact|kontakt", page["url"], re.I)))
    for page in ordered:
        if canonical_host(page["url"]) != host:
            continue
        soup = BeautifulSoup(page.get("html", ""), "html.parser")
        addresses = [unquote(urlsplit(anchor["href"]).path)
                     for anchor in soup.find_all("a", href=re.compile(r"^mailto:", re.I))]
        addresses.extend(re.findall(r"[a-z0-9._%+\-]+@[a-z0-9.-]+\.[a-z]{2,63}", page["text"], re.I))
        for address in addresses:
            if allowed.fullmatch(address) and address.casefold().split("@", 1)[1] == host:
                dossier.facts["contact_email"] = Fact(value=address, source_url=page["url"], quote=address,
                                                      basis="public_business_contact")
                return


def extract_founding(dossier, pages):
    from bs4 import BeautifulSoup
    import calendar
    brand=company_key(dossier.name).replace('haftungsbeschrankt','')
    # Dated company-history sections bind the date only to the following section,
    # never to the adjacent grant/pilot milestone.
    month_names={'januar':1,'februar':2,'märz':3,'april':4,'mai':5,'juni':6,'juli':7,'august':8,'september':9,'oktober':10,'november':11,'dezember':12}
    timelines=[]
    for page in pages:
        if not re.search(r'about|ueber|über|unternehmen|company',page['url'],re.I):continue
        soup=BeautifulSoup(page.get('html',''),'html.parser')
        for h in soup.find_all(re.compile(r'^h[1-6]$')):
            heading=h.get_text(' ',strip=True)
            stamp=re.search(r'\b('+'|'.join(month_names)+r')\s+(20\d{2})\b',heading,re.I)
            if not stamp:continue
            section=''
            for sibling in h.next_siblings:
                if getattr(sibling,'name',None) and re.fullmatch(r'h[1-6]',sibling.name):break
                section+=sibling.get_text(' ',strip=True) if hasattr(sibling,'get_text') else str(sibling)
                if len(section)>800:break
            if company_key(dossier.name) not in company_key(section):continue
            if not re.search(r'\bgegründet\b|\bfounded\b',section,re.I) or re.search(r'geplant|plans? to|will be|soll',section,re.I):continue
            year,month=int(stamp[2]),month_names[stamp[1].casefold()]
            timelines.append((date(year,month,1),date(year,month,calendar.monthrange(year,month)[1]),page,heading))
        stat=re.search(r'(?im)^(20\d{2})\s*\n(?:Gegründet|Founded)\s*$',page['text'])
        if stat and brand in company_key(page['text']):
            year=int(stat[1]);timelines.append((date(year,1,1),date(year,12,31),page,stat.group()))
    if timelines:
        low,high,p,quote=timelines[0]
        if any(a.year!=low.year for a,b,_,_ in timelines) or (dossier.earliest_founding and dossier.earliest_founding.year!=low.year):
            dossier.issues.append('Widersprüchliche Angaben zum Unternehmensalter.')
        elif not dossier.earliest_founding:
            dossier.earliest_founding,dossier.latest_founding=low,high
            dossier.founding_basis='Datierter Gründungsabschnitt der Unternehmenswebsite; Selbstauskunft, kein Registerdatum.'
            dossier.facts['founding']=Fact(value=f'{low} bis {high}',source_url=p['url'],quote=quote,basis='company_timeline')
    claims = []
    for page in pages:
        for claim in founding_claims(page['text']):
            # Exact company reference nearby reduces confusion with customers' histories.
            pos = page['text'].find(claim['quote'])
            surroundings = page['text'][max(0, pos-150):pos+150]
            brand = company_key(dossier.name).replace('haftungsbeschrankt', '')
            if len(brand) < 5 or brand not in company_key(surroundings):
                continue
            claims.append((claim, page))
    years = {c['year'] for c, _ in claims}
    if len(years) > 1 or (years and dossier.earliest_founding and years != {dossier.earliest_founding.year}):
        dossier.issues.append('Widersprüchliche Angaben zum Unternehmensalter.')
        return
    if not dossier.earliest_founding and len(years) == 1:
        claim, page = claims[0]
        year = claim['year']
        dossier.earliest_founding, dossier.latest_founding = date(year, 1, 1), date(year, 12, 31)
        dossier.founding_basis = 'Gründungsjahr laut Unternehmenswebsite; Zeitraum, kein erfundenes Tagesdatum.'
        dossier.facts['founding'] = Fact(value=str(year), source_url=page['url'], quote=claim['quote'], basis='company_self_description')


def verify_known_identity(record, pages):
    return any(identity_match(record, p['text']) for p in pages)


def project_imprint(name, pages):
    stem = normalized(re.sub(r'\bGmbH\b|\bUG\s*\(haftungsbeschränkt\)','',name))
    for page in pages:
        if not re.search(r'impress|imprint|legal', page['url'], re.I):
            continue
        text = page['text']
        lines = [l.strip() for l in text.splitlines()]
        legal = [l for l in lines if len(l) < 120 and re.fullmatch(r'[\wÄÖÜäöüß &.,\-]+(?:GmbH|UG\s*\(haftungsbeschränkt\))',l)
                 and stem in normalized(re.split(r'\bGmbH\b|\bUG\b',l)[0])]
        register = re.search(r'\bHR[AB]\s*[:.-]?\s*\d{2,9}\s*[A-Z]{0,2}\b', text)
        court = re.search(r'(?:Amtsgericht|Registergericht|Local Court)[ :\n]+([A-ZÄÖÜ][\wÄÖÜäöüß .-]{2,55})', text)
        address = re.search(r'\b\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+', text)
        if len(set(legal)) == 1 and register and address:
            return legal[0], register.group(0).strip(), court.group(0).strip() if court else None, page
    return None


def registry_context(dossier, web, *, expected_register, expected_postcode):
    """Public register-derived page, explicitly secondary evidence, no API key.

    Exact legal name, HR number and postcode must all match before using the
    formation field. Incorporation and first-entry dates remain distinct.
    """
    from urllib.parse import quote
    slug=re.sub(r'[^a-z0-9]+','-',dossier.name.lower().replace('ü','ue').replace('ä','ae').replace('ö','oe')).strip('-')
    page=web.try_page('https://www.registercheck.de/companies/'+quote(slug),'register_secondary')
    if not page:return None
    text=page['text']
    if normalized(dossier.name) not in normalized(text) or normalized(expected_register) not in normalized(text) or expected_postcode not in text:return None
    # The site's explanatory label makes the meaning explicit.
    match=re.search(r'Gründung\s+(?:Datum des Gesellschaftsvertrags oder der Satzung[^\d]{0,100})?(\d{2}\.\d{2}\.\d{4})',text,re.I)
    if match:
        dd,mm,yyyy=map(int,match.group(1).split('.'))
        when=date(yyyy,mm,dd)
        dossier.earliest_founding=dossier.latest_founding=when
        dossier.founding_basis='Gesellschaftsvertrag/Satzung laut Registercheck (sekundärer Registerbeleg).'
        dossier.facts['founding']=Fact(value=when.isoformat(),source_url=page['url'],quote=match.group(1),basis='register_secondary')
    if re.search(r'(?im)^(?:in Liquidation|aufgelöst|gelöscht)\s*$',text):
        dossier.facts['inactive']=Fact(value='Registerhinweis auf Liquidation/Auflösung',source_url=page['url'],quote='Liquidation/Auflösung',basis='register_secondary')
    dossier.sources.append(page['source'])
    return page
