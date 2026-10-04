from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

BASE="https://fd-ohshima.jp/reiki_2026/"
CATEGORIES=[f"{BASE}reiki_taikei/r_taikei_{i:02d}.html" for i in range(1,8)]
EXPECTED=119

class P(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.title=[]; self._title=False
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            for k,v in attrs:
                if k.lower()=="href" and v: self.links.append(v)
        if tag.lower()=="title": self._title=True
    def handle_endtag(self,tag):
        if tag.lower()=="title": self._title=False
    def handle_data(self,data):
        if self._title and data.strip(): self.title.append(data.strip())

def req(url:str,timeout=30)->tuple[bytes,str|None]:
    r=urllib.request.Request(url,headers={"User-Agent":"fire-ai-local-oshima-acquirer/1.0","Accept":"text/html,*/*"})
    with urllib.request.urlopen(r,timeout=timeout) as x:
        return x.read(),x.headers.get("Content-Type")

def decode(body:bytes,ct:str|None)->str:
    cs=None
    if ct:
        m=re.search(r"charset=([^; ]+)",ct,re.I)
        if m: cs=m.group(1).strip('"\'')
    for enc in [cs,"utf-8","cp932","shift_jis"]:
        if not enc: continue
        try: return body.decode(enc)
        except Exception: pass
    return body.decode("utf-8",errors="replace")

def sha(body:bytes)->str: return hashlib.sha256(body).hexdigest()

def discover()->list[str]:
    urls=set()
    for page in CATEGORIES:
        body,ct=req(page)
        p=P(); p.feed(decode(body,ct))
        for href in p.links:
            u=urllib.parse.urljoin(page,href)
            q=urllib.parse.urlsplit(u)
            clean=urllib.parse.urlunsplit((q.scheme,q.netloc,q.path,q.query,""))
            if q.hostname=="fd-ohshima.jp" and "/reiki_2026/reiki_honbun/" in q.path:
                urls.add(clean)
    return sorted(urls)

def fetch_one(url:str,out:Path)->dict:
    body,ct=req(url)
    text=decode(body,ct)
    p=P(); p.feed(text)
    digest=sha(body)
    path=out/"files"/f"{digest}.html"
    path.write_bytes(body)
    return {"url":url,"sha256":digest,"size_bytes":len(body),"content_type":ct,"title":" ".join(p.title),"file":str(path.relative_to(out))}

def main():
    out=Path("_acquired/oshima-reiki-fast")
    (out/"files").mkdir(parents=True,exist_ok=True)
    urls=discover()
    failures=[]; docs=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs={ex.submit(fetch_one,u,out):u for u in urls}
        for f in as_completed(futs):
            try: docs.append(f.result())
            except Exception as e: failures.append({"url":futs[f],"error":type(e).__name__,"message":str(e)[:300]})
    docs.sort(key=lambda x:x["url"])
    manifest={
      "bundle_format":"fire-ai-local-regulation-snapshot-v1",
      "profile_code":"oshima-fire-union",
      "source":"大島地区消防組合例規集",
      "official_root":BASE,
      "content_current_date":"2025-04-01",
      "retrieved_at":datetime.now(timezone.utc).isoformat(),
      "expected_body_document_count":EXPECTED,
      "discovered_body_document_count":len(urls),
      "captured_body_document_count":len(docs),
      "failure_count":len(failures),
      "coverage_status":"complete" if len(urls)==EXPECTED and len(docs)==EXPECTED and not failures else "partial",
      "documents":docs,
      "failures":failures
    }
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:manifest[k] for k in ["expected_body_document_count","discovered_body_document_count","captured_body_document_count","failure_count","coverage_status"]},ensure_ascii=False))
    if manifest["coverage_status"]!="complete":
        raise SystemExit(2)

if __name__=="__main__":
    main()
