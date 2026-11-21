"""Turn archived legal notices into discovery seeds, never inferred founding dates."""
import re
from urllib.parse import urlsplit
from .core import hashid, key, ADMIN, identity_match

REGISTER = re.compile(r'\b(HR[AB])\s*[:.-]?\s*(\d{2,9})\s*([A-Z]{1,2})?\b', re.I)
NAME = re.compile(r'^(.{2,100}?\b(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|UG\s*\(haftungsbeschr[aä]nkt\)|AG))\s*[,.;]?$',re.I)
ADDRESS = re.compile(r'^(?:D[ -]|DE[ -])?(\d{5})\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß .()/\-]{2,60})$')

def register_key(text):
    m=REGISTER.search(text or '')
    return (m.group(1).upper(),m.group(2)) if m else None

def seeds(documents, known):
    by_register={}
    for company in known:
        reg=register_key(company.get('registration'))
        if reg:by_register.setdefault(reg,[]).append(company)
    output={};audit=[]
    for doc in documents:
        if 'text' not in doc:continue
        text=doc['text']; parsed=urlsplit(doc['url'])
        if parsed.scheme not in ('http','https') or not parsed.hostname:continue
        website=f'{parsed.scheme}://{parsed.netloc}/'
        registrations=list(REGISTER.finditer(text))
        matches=[]
        for match in registrations:
            for c in by_register.get(register_key(match.group()),[]):
                if identity_match(c,text):matches.append(c)
        matches={c['id']:c for c in matches}
        if len(matches)==1:
            company=dict(next(iter(matches.values())))
            company['website_candidates']=list(dict.fromkeys([website]+company['website_candidates']))
            company['archive_evidence']={k:v for k,v in doc.items() if k!='text'}
            output[company['id']]=company
            audit.append({'url':doc['url'],'status':'matched_existing_entity','id':company['id']})
            continue
        names=[];addresses=[]
        for line in text.splitlines():
            line=line.strip()
            m=NAME.fullmatch(line)
            if m and not re.search(r'copyright|©|design|powered by|vertreten durch|in trägerschaft|\bder\b',line,re.I) and len(re.findall(r'\b(?:gmbh|ggmbh|ug|ag)\b',line,re.I))==1:names.append(m.group(1))
            m=ADDRESS.fullmatch(line)
            if m:addresses.append(m.groups())
        names=list(dict.fromkeys(names));addresses=list(dict.fromkeys(addresses))
        # Multiple corporate identities or addresses are deliberately not resolved by guesswork.
        if len(names)!=1 or len(addresses)!=1 or len({register_key(m.group()) for m in registrations})!=1 or not re.search(r'\bAmtsgericht\b',text,re.I):
            audit.append({'url':doc['url'],'status':'ambiguous_or_missing_legal_identity'})
            continue
        name=names[0];postal,city=addresses[0];register=registrations[0].group().strip()
        ident='imprint-'+hashid([key(name),key(city),register_key(register)])
        company={'id':ident,'name':name,'country':'DE','city':city,'postal_code':postal,
            'founded_on':None,'founding_basis':'unknown; archive timestamp is NOT founding date',
            'registration':register,'country_source':doc['url'],'source_url':doc['url'],
            'source_name':'Company imprint via Common Crawl','country_basis':'Self-declared German court register and address; not registry-verified',
            'projects':[],'website_candidates':[website],'administrative_name_flag':bool(ADMIN.search(name)),
            'archive_evidence':{k:v for k,v in doc.items() if k!='text'}}
        output[ident]=company
        audit.append({'url':doc['url'],'status':'new_imprint_seed','id':ident})
    return list(output.values()),audit
