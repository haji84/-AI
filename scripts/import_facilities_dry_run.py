#!/usr/bin/env python3
"""Validate the legacy inspection workbook without persisting or printing PII.

Reads OOXML directly so this validator does not require Excel, JUST Calc, VBA, or openpyxl.
It checks the 611 legacy records, internal-key uniqueness, and minimum required columns.
"""
from __future__ import annotations
import argparse, hashlib, re, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(path: Path) -> None:
    with zipfile.ZipFile(path) as z:
        shared=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall(f'{{{NS}}}si'):
                shared.append(''.join((t.text or '') for t in si.iter(f'{{{NS}}}t')))
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relmap={r.attrib['Id']:r.attrib['Target'] for r in rels.findall(f'{{{PKG}}}Relationship')}
        target=None
        for s in wb.find(f'{{{NS}}}sheets'):
            if s.attrib['name']=='DB保存':
                target='xl/'+relmap[s.attrib[f'{{{RNS}}}id']]
                break
        if not target:
            raise SystemExit('DB保存 sheet not found')
        root=ET.fromstring(z.read(target))
        vals={}
        for c in root.iter(f'{{{NS}}}c'):
            ref=c.attrib.get('r',''); t=c.attrib.get('t'); v=c.find(f'{{{NS}}}v')
            if v is None: continue
            vals[ref]=shared[int(v.text)] if t=='s' else (v.text or '')

    required={'C2':'名称1メイショウ','G2':'整理番号セイリバンゴウ','I2':'所在地ショザイチ','IP2':'内部キー'}
    header_errors=[]
    for ref,expected in required.items():
        if vals.get(ref)!=expected:
            header_errors.append({'cell':ref,'expected':expected,'actual':vals.get(ref)})

    records=[]
    for row in range(3, 10000):
        name=vals.get(f'C{row}','')
        key=vals.get(f'IP{row}','')
        if name or key:
            records.append((row,name,key))
    keys=[k for _,_,k in records if k]
    blank_names=sum(1 for _,n,_ in records if not n)
    blank_keys=sum(1 for _,_,k in records if not k)
    duplicates=len(keys)-len(set(keys))
    print({
        'source_sha256':sha256(path),
        'records':len(records),
        'unique_internal_keys':len(set(keys)),
        'duplicate_internal_keys':duplicates,
        'blank_names':blank_names,
        'blank_internal_keys':blank_keys,
        'header_errors':header_errors,
        'ready_for_mapping': not header_errors and duplicates==0 and blank_keys==0,
    })

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('workbook',type=Path); args=ap.parse_args(); run(args.workbook)