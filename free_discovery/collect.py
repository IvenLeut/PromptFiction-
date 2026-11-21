from __future__ import annotations
import argparse,csv,io,json,re,time,zipfile,gzip,hashlib
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import requests
from .core import *
from .network import Fetcher,parse_html

def gleif_collect(fetch,start,end):
    """Split before the service's 10,000-result window; cache every successful page."""
    endpoint='https://api.gleif.org/api/v1/lei-records'
    exclusive_end=str(date.fromisoformat(end)+timedelta(days=1))
    params={'filter[entity.legalAddress.country]':'DE','filter[entity.creationDate]':start+'..'+exclusive_end,'page[size]':200}
    first=json.loads(fetch.get(endpoint,params,api=True,timeout=60)['text'])
    total=first['meta']['pagination']['total']
    if total>10000:
        a,b=date.fromisoformat(start),date.fromisoformat(end)
        if a==b:raise ValueError('Single-day result cap: require Golden Copy bulk input')
        mid=a+(b-a)//2
        rows=gleif_collect(fetch,str(a),str(mid))+gleif_collect(fetch,str(mid+timedelta(days=1)),str(b))
        return list({row['id']:row for row in rows}.values())
    result=[];data=first
    while True:
        result.extend(data['data'])
        nxt=data.get('links',{}).get('next')
        print('GLEIF',start,end,len(result),'/',total,flush=True)
        if not nxt:break
        if urlsplit(nxt).hostname!='api.gleif.org':raise ValueError('Unexpected pagination host')
        data=json.loads(fetch.get(nxt,api=True,timeout=60)['text'])
    if len(result)!=total:raise ValueError('GLEIF response count changed; rerun in a fresh snapshot')
    return [r for r in result if start<=(r['attributes']['entity'].get('creationDate') or '')[:10]<=end]

def website_probe(company,fetch,max_domains=3,max_extra_pages=2):
    saved=[];errors=[]
    choices=list(dict.fromkeys(company['website_candidates']+domain_guesses(company['name'])))[:max_domains]
    for website in choices:
        try:
            root=fetch.get(website);home=parse_html(root['text'],root['url'])
            host=(urlsplit(root['url']).hostname or '').removeprefix('www.')
            same=lambda u:(urlsplit(u).hostname or '').removeprefix('www.')==host
            legal=[u for u in home['links'] if same(u) and re.search(r'impress|imprint|legal-notice|/legal/?$',u,re.I)]
            legal=list(dict.fromkeys(legal+[urljoin(root['url'],'/impressum')]))[:2]
            documents=[{'url':root['url'],'website':root['url'],'text':home['text']}]
            for u in legal:
                try:
                    rec=fetch.get(u);p=parse_html(rec['text'],rec['url'])
                    documents.append({'url':rec['url'],'website':root['url'],'text':p['text']})
                except Exception as exc:errors.append({'url':u,'error':type(exc).__name__})
            identity=any(identity_match(company,p['text']) for p in documents) and not any(registration_conflict(company,p['text']) for p in documents)
            if not identity:continue
            about=[u for u in home['links'] if same(u) and re.search(r'about|ueber|über|company|unternehmen|product|produkt|technology|technologie',urlsplit(u).path,re.I)]
            about=sorted(dict.fromkeys(about),key=lambda u:(not bool(re.search(r'/(?:about(?:-us)?|ueber-uns|über-uns|unternehmen|company)/?$',urlsplit(u).path,re.I)),urlsplit(u).path.count('/'),u))
            for u in about[:max_extra_pages]:
                try:
                    rec=fetch.get(u);p=parse_html(rec['text'],rec['url'])
                    documents.append({'url':rec['url'],'website':root['url'],'text':p['text']})
                except Exception as exc:errors.append({'url':u,'error':type(exc).__name__})
            for doc in documents:doc['identity_verified']=True
            saved+=documents;break
        except Exception as exc:errors.append({'url':website,'error':type(exc).__name__})
    return saved,errors

def cc_archive(fetch,website,collection):
    """Exact-domain legal-page lookup; no global wildcard crawl or first-seen=founding heuristic."""
    domain=urlsplit(website).netloc
    endpoint='https://index.commoncrawl.org/'+collection+'-index'
    rec=fetch.get(endpoint,{'url':domain+'/impressum*','output':'json','filter':'status:200'},api=True,timeout=30)
    records=[json.loads(line) for line in rec['text'].splitlines() if line.strip()]
    if not records:return None
    record=sorted(records,key=lambda r:(r['timestamp'],r['url']),reverse=True)[0]
    filename=record['filename']
    if not filename.startswith('crawl-data/') or '..' in filename:raise ValueError('Invalid WARC path')
    offset,length=int(record['offset']),int(record['length'])
    if not 0<length<3_000_000:raise ValueError('WARC record too large')
    r=requests.get('https://data.commoncrawl.org/'+filename,headers={'Range':f'bytes={offset}-{offset+length-1}'},timeout=30)
    if r.status_code!=206 or len(r.content)!=length:raise ValueError('WARC range not honored')
    raw=gzip.decompress(r.content)
    first=raw.split(b'\r\n\r\n',1)[1]
    html=first.split(b'\r\n\r\n',1)[1].decode('utf-8',errors='replace')
    return {'url':record['url'],'archive_timestamp':record['timestamp'],'warc':filename,'offset':offset,'length':length,
            'text':parse_html(html,record['url'])['text']}

def cached_pages(company,root):
    """Replay only this firm's cached URLs, not every HTTP file in the research corpus."""
    urls=[p['url'] for p in company.get('page_evidence',[])]
    if not urls:return []
    urls+=company.get('website_candidates',[])+domain_guesses(company['name'])
    documents={};seen=set()
    for depth in range(2):
        extra=[]
        for url in dict.fromkeys(urls):
            if url in seen:continue
            seen.add(url)
            normalized=requests.Request('GET',url).prepare().url
            path=root/(hashlib.sha256(normalized.encode()).hexdigest()+'.json')
            if not path.exists():continue
            rec=json.loads(path.read_text(encoding='utf-8'))
            if 'text' not in rec:continue
            page=parse_html(rec['text'],rec['url'])
            documents[rec['url']]={'url':rec['url'],'text':page['text'],'sha256':rec['sha256'],'retrieved_at':rec['retrieved_at']}
            extra += [u for u in page['links'] if re.search('impress|imprint|about|ueber|über|company|unternehmen|product|produkt|technology|technologie',urlsplit(u).path,re.I)]
        urls=extra
    requested={p['url'] for p in company.get('page_evidence',[])}
    pages=[d for d in documents.values() if d['url'] in requested]
    matched=any(identity_match(company,p['text']) for p in pages) and not any(registration_conflict(company,p['text']) for p in pages)
    for page in pages:page.update(identity_verified=matched,website=company.get('website'))
    return pages

def export(companies,out,start,end,target):
    out.mkdir(parents=True,exist_ok=True)
    if len({c['id'] for c in companies})!=len(companies):raise ValueError('Duplicate company IDs in research results')
    qualified=sorted([c for c in companies if c.get('status')=='qualified_candidate'],key=lambda c:c['id'])
    reviews=sorted([c for c in companies if c.get('status')!='qualified_candidate'],key=lambda c:c['id'])
    dump(out/'qualified.json',qualified);dump(out/'review_queue.json',reviews)
    bysector={s:sorted([c for c in qualified if s in c['industries']],key=lambda c:c['id'])[:target] for s in SECTORS}
    raw=[]
    for sector,rows in bysector.items():
        leads=[]
        for c in rows:
            evidence=next(e for e in c['innovation_evidence'] if sector in e['sectors'])
            founded=c.get('founded_on')
            year=int(founded[:4]) if founded else c['founding_claims'][0]['year']
            signal=[{'source':c['source_name'],'type':'entity_identity','url':c['source_url'],
                'evidence':f"{c['name']}; legal address {c['city']}, DE; creation date {founded or 'unknown'}"},
                {'source':'Company website','type':'technology_self_description','url':evidence['url'],'evidence':evidence['quote']}]
            lead={'id':c['id'],'name':c['name'],'description':evidence['quote'],'industry':sector,'country':'DE','location':c['city'],
                'source_url':c['source_url'],'source_name':c['source_name'],'discovery_source':'open_data_v1','initial_signal':'Open-data identity + matched company website',
                'country_evidence':{'source':c['source_name'],'url':c['country_source'],'finding':f"Legal address: {c['city']}, DE",'field':'country','verification_status':'source_matched'},
                'is_demo':False,'website':c['website'],'founding_year':year,'signals':signal,
                'prioritization_reason':'Recent legal entity with technical self-description; business age and innovation merit require diligence.'}
            leads.append(lead);raw.append(lead)
        dump(out/(sector.replace(' / ','_').replace('/','_')+'.json'),leads)
    dump(out/'raw_leads.json',list({r['id']:r for r in reversed(raw)}.values()))
    mapping=[];longlist=[]
    with (out/'longlist.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f,delimiter=';');writer.writerow(HEADERS)
        for i,c in enumerate(qualified,2):
            quote=c['innovation_evidence'][0]['quote']
            values=[None,'Noch nicht bewertet',None,None,'Unbekannt',quote,None]
            if quote.lstrip().startswith(('=','+','-','@')):quote="'"+quote
            writer.writerow([*values[:5],quote,values[6]])
            mapping.append({'row':i,'id':c['id'],'name':c['name'],'website':c['website']})
            longlist.append({'id':c['id'],'name':c['name'],'industries':c['industries'],'website':c['website'],
                'columns':dict(zip(HEADERS,values)),
                'founding_basis':c.get('founding_basis'),'founded_on':c.get('founded_on'),
                'source_url':c['source_url'],'status':'research_candidate'})
    dump(out/'row_map.json',mapping)
    dump(out/'longlist.json',longlist)
    report={'as_of':end,'founded_from':start,'target_per_industry':target,'researched_unique':len(companies),'qualified_unique':len(qualified),
       'review_required':len(reviews),'per_industry':{s:len(rows) for s,rows in bysector.items()},
       'shortfall':{s:max(0,target-len(rows)) for s,rows in bysector.items()},'llm_calls':0,'paid_api_calls':0,
       'national_completeness':False,'undiscovered_by_investors_verified':False,
       'scores':'null: discovery evidence does not support investment or market scoring',
       'identity_matched_websites':sum(bool(c.get('identity_verified')) for c in companies),
       'date_conflicts':sum(bool(c.get('date_conflict')) for c in companies),
       'qualification':'Rule-based research candidates, not independently verified innovative startups',
       'target_met':all(len(rows)>=target for rows in bysector.values())}
    dump(out/'report.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['download','run','export','archive','recheck'])
    p.add_argument('--work',type=Path,default=Path('data/open-discovery'));p.add_argument('--out',type=Path,default=Path('data/open-discovery/export'))
    p.add_argument('--start',default='2024-11-20');p.add_argument('--end',default='2026-11-20');p.add_argument('--target',type=int,default=200)
    p.add_argument('--max-companies',type=int,default=400);p.add_argument('--workers',type=int,default=6);p.add_argument('--max-domains',type=int,default=3)
    p.add_argument('--offline',action='store_true');p.add_argument('--website');p.add_argument('--collection',default='CC-MAIN-2026-43')
    p.add_argument('--include-unmatched-names',action='store_true',help='Also research GLEIF names without sector words; larger network budget')
    p.add_argument('--archive-imprints',type=Path,help='Common Crawl imprints.json to match and add as discovery seeds')
    p.add_argument('--supplemental-sources',type=Path,help='Audited same-site source URLs for existing IDs; used during recheck')
    p.add_argument('--qualified-only',action='store_true',help='Recheck only current qualified candidates; for restrictive rule additions, not a full replay')
    p.add_argument('--quality-holds',type=Path,help='Evidence-backed audit holds for existing IDs; can only exclude, never add a company')
    a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True);fetch=Fetcher(a.work/'http',a.offline)
    if not 1<=a.target<=200 or a.workers<1 or a.max_companies<1 or a.max_domains<1:p.error('Positive budgets required; target must be 1..200')
    if date.fromisoformat(a.start)>date.fromisoformat(a.end):p.error('start must not exceed end')
    if a.command=='download':
        rows=gleif_collect(fetch,a.start,a.end);dump(a.work/'gleif.json',rows)
        url='https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip'
        if not (a.work/'cordis.zip').exists():
            r=requests.get(url,timeout=180);r.raise_for_status();zipfile.ZipFile(io.BytesIO(r.content));(a.work/'cordis.zip').write_bytes(r.content)
        return
    if a.command=='archive':
        if not a.website:p.error('--website required')
        dump(a.work/'archive-result.json',cc_archive(fetch,a.website,a.collection));return
    checkpoints=a.work/'companies';checkpoints.mkdir(exist_ok=True)
    if a.command=='run':
        gl=[gleif_row(r,a.start,a.end) for r in json.loads((a.work/'gleif.json').read_text(encoding='utf-8'))];gl=[r for r in gl if r]
        co=read_cordis(a.work/'cordis.zip',a.start);companies=merge_sources(gl,co)
        archive_seeds=[]
        if a.archive_imprints:
            from .imprints import seeds
            archive_seeds,audit=seeds(json.loads(a.archive_imprints.read_text(encoding='utf-8')),companies)
            dump(a.work/'archive_seed_audit.json',audit)
            byid={c['id']:c for c in companies};byid.update({c['id']:c for c in archive_seeds});companies=list(byid.values())
        # Name-based terms only schedule research. They never qualify a lead.
        dump(a.work/'all_entities.json',companies)
        eligible=[c for c in companies if a.include_unmatched_names or c.get('archive_evidence') or c['projects'] or industries(c['name']) or re.search('tech|digital|innovation|systems|labs|data|solutions',c['name'],re.I)]
        eligible.sort(key=lambda c:(bool(c['administrative_name_flag']),not bool(c.get('founded_on')),not bool(c['website_candidates']),not bool(industries(c['name'])),c['id']))
        selected=eligible[:a.max_companies]
        dump(a.work/'discovery_manifest.json',{'gleif_entities':len(gl),'cordis_smes':len(co),'archive_seeds':len(archive_seeds),'merged_entities':len(companies),'researchable':len(eligible),'scheduled':len(selected),'start':a.start,'end':a.end})
        def task(c):
            path=checkpoints/(hashid([c['id'],a.start,a.end,'v1'])+'.json')
            if path.exists() and not c.get('archive_evidence'):
                cached=json.loads(path.read_text(encoding='utf-8'))
                return assess(cached,cached_pages(cached,a.work/'http'),a.start,a.end)
            pages,errors=website_probe(c,fetch,a.max_domains)
            result=assess(c,pages,a.start,a.end);result['fetch_errors']=errors
            result['page_evidence']=[{'url':p['url'],'identity_verified':p['identity_verified']} for p in pages]
            dump(path,result);return result
        results=[]
        with ThreadPoolExecutor(max_workers=min(a.workers,8)) as pool:
            jobs={pool.submit(task,c):c for c in selected}
            for future in as_completed(jobs):
                c=jobs[future]
                try:result=future.result()
                except Exception as exc:result={**c,'status':'review_required','open_questions':[str(exc)],'industries':[]}
                results.append(result)
                if len(results)%50==0 or len(results)==len(selected):print('RESEARCH',len(results),'/',len(selected),flush=True)
        dump(a.work/'results.json',sorted(results,key=lambda c:c['id']))
    results=json.loads((a.work/'results.json').read_text(encoding='utf-8'))
    if a.command=='recheck':
        if a.quality_holds:
            byid={c['id']:c for c in results}
            for item in json.loads(a.quality_holds.read_text(encoding='utf-8')):
                if not item.get('reason') or not item.get('source_url','').startswith('https://'):raise ValueError('Audit hold requires reason and source URL')
                byid[item['id']]['quality_hold']=item
        if a.supplemental_sources:
            byid={c['id']:c for c in results}
            for item in json.loads(a.supplemental_sources.read_text(encoding='utf-8')):
                company=byid[item['id']]
                expected=(urlsplit(company.get('website') or '').hostname or '').removeprefix('www.')
                if not expected or (urlsplit(item['url']).hostname or '').removeprefix('www.')!=expected:raise ValueError('Supplement must be on the matched company website')
                rec=fetch.get(item['url'])
                if (urlsplit(rec['url']).hostname or '').removeprefix('www.')!=expected:raise ValueError('Supplement redirected off the matched site')
                company.setdefault('page_evidence',[]).append({'url':rec['url'],'identity_verified':True})
        def replay(c):
            if a.qualified_only and c.get('status')!='qualified_candidate':return c
            pages=cached_pages(c,a.work/'http')
            c['page_evidence']=[{k:v for k,v in p.items() if k not in ('text','website')} for p in pages]
            return assess(c,pages,a.start,a.end)
        replayed=[]
        with ThreadPoolExecutor(max_workers=min(a.workers,8)) as pool:
            for i,c in enumerate(pool.map(replay,results),1):
                replayed.append(c)
                if i%100==0 or i==len(results):print('RECHECK',i,'/',len(results),flush=True)
        results=replayed
        dump(a.work/'results.json',results)
        for company in results:
            dump(checkpoints/(hashid([company['id'],a.start,a.end,'v1'])+'.json'),company)
    export(results,a.out,a.start,a.end,a.target)
    if (a.work/'discovery_manifest.json').exists():dump(a.out/'discovery_manifest.json',json.loads((a.work/'discovery_manifest.json').read_text(encoding='utf-8')))

if __name__=='__main__':main()
