"""Cached public HTTP access; bounded requests, robots checks, no credentials."""
import hashlib,json,time,socket,ipaddress,threading
from pathlib import Path
from urllib.parse import urlsplit,urljoin,urldefrag
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup

class Fetcher:
    def __init__(self,root,offline=False):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.offline=offline;self.robots={};self.lock=threading.Lock();self.last={}
    def get(self,url,params=None,api=False,timeout=15,max_bytes=3_000_000):
        url=requests.Request('GET',url,params=params).prepare().url
        ident=hashlib.sha256(url.encode()).hexdigest();path=self.root/(ident+'.json')
        if path.exists():
            rec=json.loads(path.read_text(encoding='utf-8'))
            if rec.get('error'):raise ValueError(rec['error'])
            return rec
        if self.offline:raise ValueError('Not cached: '+url)
        original=url
        try:
            for hop in range(4):
                p=urlsplit(url)
                if p.scheme not in ('http','https') or p.username or p.password or p.port not in (None,80,443):raise ValueError('Unsafe URL')
                addresses=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Non-public destination')
                if not api:self.check_robots(url)
                with self.lock:
                    delay=max(0,self.last.get(p.hostname,0)+.8-time.monotonic())
                    if delay:time.sleep(delay)
                    self.last[p.hostname]=time.monotonic()
                r=requests.get(url,headers={'User-Agent':'FounderRadarResearch/1.0'},timeout=timeout,allow_redirects=False,stream=True)
                if r.status_code in (301,302,303,307,308):
                    url=urljoin(url,r.headers.get('Location',''));r.close();continue
                r.raise_for_status()
                chunks=[];size=0
                for chunk in r.iter_content(65536):
                    size+=len(chunk)
                    if size>max_bytes:r.close();raise ValueError('Response too large')
                    chunks.append(chunk)
                body=b''.join(chunks)
                rec={'url':url,'requested_url':original,'status':r.status_code,'retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                     'sha256':hashlib.sha256(body).hexdigest(),'text':body.decode('utf-8',errors='replace')}
                r.close();path.write_text(json.dumps(rec,ensure_ascii=False),encoding='utf-8');return rec
            raise ValueError('Too many redirects')
        except Exception as exc:
            path.write_text(json.dumps({'url':original,'error':type(exc).__name__+': '+str(exc)}),encoding='utf-8');raise
    def check_robots(self,url):
        p=urlsplit(url);origin=p.scheme+'://'+p.netloc
        if origin not in self.robots:
            try:
                rec=self.get(origin+'/robots.txt',api=True,timeout=8,max_bytes=300000)
                rp=RobotFileParser();rp.parse(rec['text'].splitlines());self.robots[origin]=rp
            except requests.HTTPError as exc:
                if exc.response.status_code==404:self.robots[origin]=None
                else:raise ValueError('robots unavailable')
            except ValueError as exc:
                if '404 Client Error' in str(exc):self.robots[origin]=None
                else:raise
        rp=self.robots[origin]
        if rp is not None and not rp.can_fetch('FounderRadarResearch',url):raise ValueError('robots disallow')

def parse_html(html,url):
    soup=BeautifulSoup(html,'html.parser')
    for el in soup(['script','style','noscript','svg','template']):el.decompose()
    links=[urldefrag(urljoin(url,a['href']))[0] for a in soup.select('a[href]')]
    # Preserve a sentence split by visual emphasis without joining separate paragraphs.
    for el in soup(['span','strong','b','em','i','a','small','mark','u','sup','sub']):el.unwrap()
    soup.smooth()
    return {'text':'\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip()),'links':list(dict.fromkeys(links))}
