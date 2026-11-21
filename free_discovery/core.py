from __future__ import annotations
import csv, hashlib, io, json, re, unicodedata, zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

SECTORS = {
 'AI / Software': ['software','saas','artificial intelligence','machine learning','deep learning','computer vision','künstliche intelligenz','ki','ai','neural network','language model','digital platform','webbasiert','web-based'],
 'ClimateTech': ['battery','batteries','batterie','hydrogen','wasserstoff','decarbon','carbon capture','co2','photovolta','solar','renewable','erneuerbar','recycling','circular economy','energy storage','energiespeicher','heat pump','wärmepump','geothermal'],
 'HealthTech': ['medical','medizin','diagnos','therapeutic','therapeutisch','biotech','drug discovery','patient','digital health','healthcare','biosensor','pharma','clinical','klinisch'],
 'FinTech': ['fintech','insurtech','regtech','payment','zahlungs','banking','financial technology','financial software','finanzsoftware','fraud detection','digital asset','tokenization','tokenisierung'],
 'Industrial / DeepTech': ['robot','industrial','industri','manufactur','fertigung','semiconductor','halbleiter','photon','quantum','quanten','sensor','automation','automatisier','3d print','3d-druck','aerospace','spacecraft','nanotech','material science']
}
TECH = re.compile(r'\b(?:develop\w*|entwick\w*|proprietary|patent\w*|algorithm\w*|technolog\w*|platform\w*|plattform\w*|prototype\w*|prototyp\w*|webbasier\w*|web-based|integrationslös\w*)\b', re.I)
LEGAL = re.compile(r'\b(?:gmbh|ug|ag|se|kg|ohg|gbr|mbh|ltd)\b|haftungsbeschränkt', re.I)
ADMIN = re.compile(r'holding|beteiligung|vermögens|vermoegens|verwaltung|immobilien|family office|stiftung|investment|capital|ventures|windpark|solarpark|energiepark',re.I)
HEADERS=['Score','Risiko','Marktpotenzialscore','Unternehmensscore','Stage Einordnung','Produktbeschreibung / Value Proposition','Investmenthypothese']

def key(text):
    text=unicodedata.normalize('NFKD',text.casefold().replace('ß','ss'))
    return re.sub('[^a-z0-9]','',text)

def company_key(text):
    return key(LEGAL.sub('',text))

def hashid(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:24]

def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def industries(text):
    hits={sector:[t for t in terms if re.search(r'(?<!\w)'+re.escape(t)+(r'(?!\w)' if len(t)<=3 else ''),text,re.I)] for sector,terms in SECTORS.items()}
    industrial=hits.get('Industrial / DeepTech',[])
    if industrial and all(term in ('automation','automatisier','industri','industrial') for term in industrial):
        if not re.search(r'\b(?:maschinen?\w*|anlagen?\w*|produktion\w*|fertigung\w*|robot\w*|sensor\w*|manufactur\w*|factory|factories|wärme\w*|strom\w*|salzspeicher|heat\w*)\b',text,re.I):hits['Industrial / DeepTech']=[]
    return {sector:terms for sector,terms in hits.items() if terms}

def founding_claims(text):
    """Only explicit formation phrases. Never copyright, grant dates or first crawl dates."""
    patterns=[r'(?:founded|established|incorporated)\s+(?:in\s+)?((?:19|20)\d{2})',
              r'(?:gegründet|Gründungsjahr|Gründung)[ \t]*[:–-]?[ \t]*(?:im Jahr(?:e)?[ \t]+)?((?:19|20)\d{2})',
              r'((?:19|20)\d{2})\s+(?:(?:in|als)\s+[\wäöüÄÖÜß -]{1,35}\s+)?gegründet',
              r'wurde\s+(?:im Jahr(?:e)?\s+)?((?:19|20)\d{2})\s+[^.!?\n]{0,120}?gegründet']
    return [{'year':int(m.group(1)),'quote':m.group(0)} for p in patterns for m in re.finditer(p,text,re.I)]

def gleif_row(raw,start,end):
    e=raw['attributes']['entity']; created=e.get('creationDate')
    if not created or e['legalAddress'].get('country')!='DE': return None
    # The UTC date is retained as supplied, never substituted by LEI issue date.
    day=created[:10]
    if not start<=day<=end or e.get('category') in ('FUND','BRANCH') or e.get('status')!='ACTIVE':return None
    return {'id':'gleif-'+raw['id'],'lei':raw['id'],'name':e['legalName']['name'],
            'country':'DE','city':e['legalAddress'].get('city'), 'postal_code':e['legalAddress'].get('postalCode'),
            'founded_on':day,'founding_basis':'GLEIF entity.creationDate; original business age not independently verified',
            'registration':e.get('registeredAs'),'registration_authority':e.get('registeredAt',{}).get('id'),
            'country_source':raw['links']['self'],'source_url':raw['links']['self'],
            'source_name':'GLEIF','projects':[], 'website_candidates':[],
            'administrative_name_flag':bool(ADMIN.search(e['legalName']['name']))}

def read_cordis(path,start):
    z=zipfile.ZipFile(path)
    def rows(name):return csv.DictReader(io.TextIOWrapper(z.open(name),encoding='utf-8-sig'),delimiter=';')
    projects={r['id']:r for r in rows('project.csv')}
    firms={}
    for r in rows('organization.csv'):
        p=projects.get(r['projectID'])
        if r['country']!='DE' or r['activityType']!='PRC' or r.get('SME')!='true' or not p:continue
        if (p.get('endDate') or '')<start:continue
        f=firms.setdefault(r['organisationID'],{'id':'cordis-'+r['organisationID'],'name':r['name'],'country':'DE','city':r['city'],'postal_code':r['postCode'],
             'founded_on':None,'founding_basis':'unknown; project dates are NOT incorporation dates',
             'registration':None,'country_source':'https://cordis.europa.eu/project/id/'+r['projectID'],
             'source_url':'https://cordis.europa.eu/project/id/'+r['projectID'],'source_name':'CORDIS',
             'projects':[],'website_candidates':[],'administrative_name_flag':bool(ADMIN.search(r['name']))})
        if r.get('organizationURL'):
            u=r['organizationURL'].strip(); u=u if '://' in u else 'https://'+u
            if u not in f['website_candidates']:f['website_candidates'].append(u)
        f['projects'].append({'id':p['id'],'title':p['title'],'objective':p['objective'],'start':p['startDate'],
             'role':r['role'],'url':'https://cordis.europa.eu/project/id/'+p['id']})
    return list(firms.values())

def merge_sources(gleif,cordis):
    byname={}
    for g in gleif:byname.setdefault(key(g['name']),[]).append(g)
    output=list(gleif)
    for c in cordis:
        matches=byname.get(key(c['name']),[])
        if len(matches)==1 and key(matches[0]['city'] or '')==key(c['city'] or ''):
            g=matches[0];g['projects']+=c['projects'];g['website_candidates']+=c['website_candidates']
        else:output.append(c)
    return output

def domain_guesses(name):
    """Candidates only. They NEVER become website facts without matching legal identity."""
    stem=LEGAL.sub('',name).replace('(haftungsbeschränkt)','')
    stem=stem.strip(' ()&.,-')
    words=re.findall(r'[a-z0-9]+',stem.casefold().translate(str.maketrans({'ä':'ae','ö':'oe','ü':'ue','ß':'ss'})))
    if not words or len(words)>5:return []
    bases=list(dict.fromkeys([''.join(words),'-'.join(words)]))
    return ['https://'+b+tld for tld in ('.de','.com','.ai','.io') for b in bases if len(b)>2]

def registration_conflict(company,text):
    """An explicit conflicting register number cannot be rescued by an address match."""
    expected=re.search(r'\b(HRB|HRA|GnR|PR|VR)\s*([0-9]+)',company.get('registration') or '',re.I)
    if not expected or key(company['name']) not in key(text):return False
    observed=re.findall(r'\b'+re.escape(expected.group(1))+r'\s*([0-9]+)',text,re.I)
    return bool(observed and expected.group(2) not in observed)

def identity_match(company,text):
    """A legal-name match alone is insufficient for a guessed domain."""
    def contains(value):
        normalized=unicodedata.normalize('NFKD',text.casefold().replace('ß','ss'))
        normalized=''.join(x for x in normalized if not unicodedata.combining(x))
        value=unicodedata.normalize('NFKD',value.casefold().replace('ß','ss'))
        value=''.join(x for x in value if not unicodedata.combining(x))
        tokens=re.findall('[a-z]+|[0-9]+',value)
        return bool(tokens and re.search(r'(?<![a-z0-9])'+r'[^a-z0-9]*'.join(map(re.escape,tokens))+r'(?![a-z0-9])',normalized))
    if not contains(company['name']) or registration_conflict(company,text):return False
    reg=company.get('registration')
    if reg and contains(reg):return True
    city=company.get('city') or ''
    postal=company.get('postal_code') or ''
    return bool(city and postal and re.search(r'\b'+re.escape(postal)+r'\b',text) and key(city) in key(text))

def assess(company,pages,start,end):
    verified=[p for p in pages if p.get('identity_verified')]
    alltext=' '.join(p['text'] for p in verified)
    claims=[{**c,'url':p['url']} for p in verified for c in founding_claims(p['text'])]
    company['founding_claims']=claims
    years={c['year'] for c in claims}
    history=[int(m.group(1)) for m in re.finditer(r'(?:seit|since)\s+((?:19|20)\d{2})\s+(?:entwickeln wir|bieten wir|sind wir|we have|we develop|we provide)',alltext,re.I)]
    operating_years=[]
    brand=LEGAL.sub('',company['name']).strip(' ()&.,-')
    for page in verified:
        for sentence in re.split(r'(?<=[.!?])\s+|\n+',page['text']):
            if re.search(r'gründer|founder|\berfahrung\b|\bexperience\b',sentence,re.I):continue
            subject=r'(?:\bwir\b|\bwe\b|'+re.escape(brand)+')' if brand else r'(?:\bwir\b|\bwe\b)'
            duration=r'\b(?:seit|for)\s+(?:(?:über|mehr als|over|more than)\s+)?(\d{1,3})\s+(?:Jahren|years)\b'
            match=re.search(subject+r'[^.!?\n]{0,130}?'+duration,sentence,re.I)
            if not match:match=re.search(duration+r'[^.!?\n]{0,60}?'+subject,sentence,re.I)
            if match and int(match.group(1))>2:operating_years.append({'years':int(match.group(1)),'url':page['url']})
    company['claimed_operating_years']=operating_years
    conflict=bool(years and (len(years)>1 or (company.get('founded_on') and int(company['founded_on'][:4]) not in years))) or any(y<int(start[:4]) for y in history) or bool(operating_years)
    if company.get('founded_on'):
        date_ok=start<=company['founded_on']<=end and not conflict
    else:
        # Boundary years are ambiguous for a rolling two-year window.
        date_ok=bool(len(years)==1 and int(start[:4])<next(iter(years))<int(end[:4])) and not conflict
    evidence=[]
    sector_hits={}
    for p in verified:
        if re.search(r'impress|imprint|privacy|datenschutz|legal|terms|agb',urlsplit(p['url']).path,re.I):continue
        page_candidates=[]
        for sentence in re.split(r'(?<=[.!?])\s+|\n+',p['text']):
            if not 45<=len(sentence)<=1500:continue
            if re.search(r'cookies?|privacy policy|datenschutz|google analytics|all rights reserved',sentence,re.I):continue
            if re.search(r'jahresrückblick|\bnews\b|\bblog\b|zehn entwicklungen|zu ihren kernkompetenzen|seit mehr als \d+ jahren',sentence,re.I):continue
            if re.search(r'\b(?:hat er|hat sie|his research|her research)\b',sentence,re.I):continue
            if re.search(r'\bzuständig\b|\bverantwort\w*\b|\bnetzwerk\b|\bverband\b|with backgrounds|background in',sentence,re.I):continue
            if re.search(r'\b(?:strategien|strategies|verkaufs.trainings|marketingmaßnahmen)\b',sentence,re.I) and not re.search(r'software|plattform|platform|algorithm|prototyp|produkt|product',sentence,re.I):continue
            if re.search(r'integrated into[^.!?]{0,100}[’\x27]s[^.!?]{0,60}platform',sentence,re.I):continue
            if re.search(r'besonders gute chancen haben|förderfähige branchen|eligible sectors',sentence,re.I):continue
            hits=industries(sentence)
            if hits and TECH.search(sentence):
                own=bool(re.search(r'\b(?:wir|we)\s+(?:entwickeln|bauen|develop|build)|\binhouse\b|\bis building\b',sentence,re.I))
                named=bool(company_key(company['name']) and company_key(company['name']) in key(sentence))
                record={'url':p['url'],'quote':' '.join(sentence.split()[:22]),'sectors':list(hits),'basis':'company self-description','own_development_language':own,'company_named':named}
                page_candidates.append(((own or named,own,len(sentence.split())>=10),hits,record))
        if page_candidates:
            chosen={}
            for sector in SECTORS:
                matches=[item for item in page_candidates if sector in item[1]]
                if matches:
                    _,hits,record=max(matches,key=lambda c:c[0])
                    chosen[record['quote']]=(hits,record)
            for hits,record in chosen.values():
                for sector,terms in hits.items():sector_hits.setdefault(sector,[]).extend(terms)
                evidence.append(record)
    # CORDIS is evidence of participation, NOT proof that all consortium technology is this firm's product.
    company['industry_hints']=industries(' '.join(p['title']+' '+p['objective'] for p in company['projects'])+' '+company['name'])
    company['industries']=sorted(sector_hits)
    company['innovation_evidence']=sorted(evidence,key=lambda e:(not e['own_development_language'],not e['company_named']))[:12]
    company['website']=verified[0]['website'] if verified else None
    company['identity_verified']=bool(verified)
    company['date_conflict']=conflict
    business_model=bool(re.search(r'\b(?:wir erwerben|we acquire)\b[^.!?\n]{0,220}\b(?:\w*unternehmen|companies|businesses)\b|\bwe aim to be\b[^.!?\n]{0,100}\bIPP\b',alltext,re.I))
    company['administrative_activity_flag']=business_model
    company['status']='qualified_candidate' if date_ok and evidence and verified and not company.get('administrative_name_flag') and not business_model and not company.get('quality_hold') else 'review_required'
    company['open_questions']=[q for condition,q in [
        (not date_ok,'Gründung im exakten Zweijahresfenster nicht widerspruchsfrei belegt'),
        (conflict,'Datumswiderspruch: rechtliche Entstehung und Unternehmensgeschichte prüfen'),
        (not verified,'Website rechtlich nicht sicher zugeordnet'),
        (not evidence,'Eigene technische Leistung noch nicht belegt'),
        (company.get('administrative_name_flag'),'Holding-/Verwaltungs-/Projektgesellschaft prüfen')
        ,(business_model,'Unternehmenskäufer oder Energieportfolio-Betreiber; eigene Technologie nicht aus KI-Nennung ableiten')
        ,(company.get('quality_hold'),'Qualitätsprüfung zurückgestellt: '+company.get('quality_hold',{}).get('reason',''))
    ] if condition]
    return company
