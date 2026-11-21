"""Direct Common Crawl index-block reader; avoids the public CDX query service.

Only public bulk files and byte ranges. Fixed crawl + selection seed make the
sample reproducible; a sampled index is explicitly NOT national coverage.
"""
import argparse,bisect,gzip,hashlib,json,re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
import requests
from .core import dump
from .network import parse_html

def range_bytes(url,offset,length):
    r=requests.get(url,headers={'Range':f'bytes={offset}-{offset+length-1}','User-Agent':'FounderRadarResearch/1.0'},timeout=45)
    if r.status_code!=206 or len(r.content)!=length:raise ValueError('Server did not honor byte range')
    return r.content

def prepare(root,crawl):
    root=Path(root)/crawl;root.mkdir(parents=True,exist_ok=True)
    base=f'https://data.commoncrawl.org/cc-index/collections/{crawl}/indexes/'
    idx=root/'cluster.idx'
    if not idx.exists():
        r=requests.get(base+'cluster.idx',timeout=180);r.raise_for_status();idx.write_bytes(r.content)
    rows=[]
    with idx.open(encoding='utf-8') as f:
        for line in f:
            key,filename,offset,length,*_=line.rstrip().split('\t')
            rows.append((key,filename,int(offset),int(length)))
    return root,base,rows

def block(root,base,row):
    key,filename,offset,length=row
    if not re.fullmatch(r'cdx-\d+\.gz',filename):raise ValueError('Invalid index file')
    path=root/f'{filename}-{offset}.gz'
    if not path.exists():path.write_bytes(range_bytes(base+filename,offset,length))
    result=[]
    for line in gzip.decompress(path.read_bytes()).decode().splitlines():
        surt,timestamp,data=line.split(' ',2)
        record=json.loads(data)
        record['timestamp']=timestamp
        record['surt']=surt
        result.append(record)
    return result

def warc(root,record):
    filename=record['filename'];offset=int(record['offset']);length=int(record['length'])
    if not filename.startswith('crawl-data/') or '..' in filename or not 0<length<3_000_000:raise ValueError('Unsafe WARC reference')
    identity=hashlib.sha256(f'{filename}:{offset}'.encode()).hexdigest()
    path=root/(identity+'.warc.gz')
    if not path.exists():path.write_bytes(range_bytes('https://data.commoncrawl.org/'+filename,offset,length))
    data=gzip.decompress(path.read_bytes());http=data.split(b'\r\n\r\n',1)[1]
    header,body=http.split(b'\r\n\r\n',1)
    # Common Crawl may retain the origin encoding header after decoding the body.
    if body.startswith(b'\x1f\x8b'):body=gzip.decompress(body)
    text=parse_html(body.decode('utf-8',errors='replace'),record['url'])['text']
    return {'url':record['url'],'timestamp':record['timestamp'],'warc':filename,'offset':offset,'length':length,'text':text}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('data/commoncrawl'));p.add_argument('--crawl',default='CC-MAIN-2026-43')
    p.add_argument('--blocks',type=int,default=64);p.add_argument('--documents',type=int,default=100);p.add_argument('--host')
    a=p.parse_args();root,base,rows=prepare(a.root,a.crawl)
    if a.host:
        prefix=','.join(reversed(a.host.removeprefix('www.').split('.')))+')/'
        keys=[r[0] for r in rows];at=max(0,bisect.bisect_left(keys,prefix)-1)
        selected=rows[at:at+2]
    else:
        german=[r for r in rows if r[0].startswith('de,')]
        selected=sorted(german,key=lambda r:hashlib.sha256(r[0].encode()).hexdigest())[:a.blocks]
    records={};errors=[]
    for n,row in enumerate(selected,1):
        try:
            for r in block(root,base,row):
                host=urlsplit(r['url']).hostname or ''
                if r.get('status')!='200' or not re.search('impressum|imprint',urlsplit(r['url']).path,re.I):continue
                if a.host and host.removeprefix('www.')!=a.host.removeprefix('www.'):continue
                if not a.host and not host.endswith('.de'):continue
                records.setdefault(host,r)
        except Exception as exc:errors.append({'block':row[0],'error':str(exc)})
        print('INDEX',n,len(selected),'imprints',len(records),flush=True)
    dump(root/'imprint_index.json',list(records.values()))
    # Reproducible sample of domains, not top-ranked/curated startups.
    chosen=sorted(records.values(),key=lambda r:hashlib.sha256(r['url'].encode()).hexdigest())[:a.documents]
    def task(record):
        try:return warc(root,record)
        except Exception as exc:return {'url':record['url'],'error':str(exc)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        docs=list(pool.map(task,chosen))
    dump(root/'imprints.json',docs)
    dump(root/'report.json',{'crawl':a.crawl,'sampled_blocks':len(selected),'imprint_domains':len(records),'downloaded_documents':sum('text'in d for d in docs),'errors':errors,'complete':False})
    print('ARCHIVE COMPLETE',len(records),len(docs),flush=True)

if __name__=='__main__':main()
