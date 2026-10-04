#!/usr/bin/env python3
"""PII-safe structural audit for 救急報告関係.xlsm.
Only outputs counts, column counts, key completeness, and duplicate statistics.
"""
from __future__ import annotations
import argparse, re, zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
KEYS={
    'CSV_事案台帳':['A','B','C'],
    'CSV_救護者台帳':['A','B','C','D'],
    'CSV_出動隊員':['A','B','C','D','E'],
}

def cell_value(c, shared):
    t=c.attrib.get('t'); v=c.find(f'{{{NS}}}v')
    if v is None: return ''
    return shared[int(v.text)] if t=='s' else (v.text or '')

def run(path: Path):
    with zipfile.ZipFile(path) as z:
        shared=[]
        sr=ET.fromstring(z.read('xl/sharedStrings.xml'))
        for si in sr.findall(f'{{{NS}}}si'):
            shared.append(''.join((t.text or '') for t in si.iter(f'{{{NS}}}t')))
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relmap={r.attrib['Id']:r.attrib['Target'] for r in rels.findall(f'{{{PKG}}}Relationship')}
        result={}
        for s in wb.find(f'{{{NS}}}sheets'):
            name=s.attrib['name']
            if name not in KEYS: continue
            root=ET.fromstring(z.read('xl/'+relmap[s.attrib[f'{{{RNS}}}id']]))
            header_count=0; rows={}; keycols=KEYS[name]
            for c in root.iter(f'{{{NS}}}c'):
                ref=c.attrib.get('r',''); m=re.match(r'([A-Z]+)(\d+)$',ref)
                if not m: continue
                col,row=m.group(1),int(m.group(2))
                if row==1:
                    if cell_value(c,shared): header_count += 1
                    continue
                if col in keycols:
                    rows.setdefault(row,{})[col]=cell_value(c,shared).strip()
            keys=[]; missing=Counter()
            for d in rows.values():
                miss=tuple(c for c in keycols if not d.get(c,''))
                if miss: missing[miss]+=1
                else: keys.append(tuple(d.get(c,'') for c in keycols))
            counts=Counter(keys)
            result[name]={
                'rows':len(rows), 'columns':header_count, 'complete_keys':len(keys),
                'unique_keys':len(counts),
                'duplicate_key_values':sum(1 for v in counts.values() if v>1),
                'missing_key_patterns':{'/'.join(k):v for k,v in missing.items()},
            }
        print(result)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('workbook',type=Path); a=p.parse_args(); run(a.workbook)