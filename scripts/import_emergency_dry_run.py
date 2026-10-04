#!/usr/bin/env python3
"""Dry-run validator for the legacy emergency CSV exports.
Does not persist row values and does not print PII. It validates headers and unique source keys only.
"""
from __future__ import annotations
import argparse, csv, hashlib
from pathlib import Path

REQUIRED={
 "cases":{"覚知年月","署所ｺｰﾄﾞ","出場番号"},
 "patients":{"覚知年月","署所ｺｰﾄﾞ","出場番号","救護者番号"},
 "crew":{"覚知年月","署所ｺｰﾄﾞ","出場番号","隊員種別","隊員ｺｰﾄﾞ"},
}

def normalize(v:str)->str: return (v or "").strip()
def file_sha256(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()

def run(kind:str,path:Path):
 with path.open('r',encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f); headers=set(reader.fieldnames or [])
  missing=REQUIRED[kind]-headers
  if missing: raise SystemExit(f"missing required columns: {sorted(missing)}")
  seen=set(); rows=dupes=blank=0
  for row in reader:
   rows+=1
   base=(normalize(row.get('覚知年月','')),normalize(row.get('署所ｺｰﾄﾞ','')),normalize(row.get('出場番号','')))
   if kind=='patients': key=base+(normalize(row.get('救護者番号','')),)
   elif kind=='crew': key=base+(normalize(row.get('隊員種別','')),normalize(row.get('隊員ｺｰﾄﾞ','')))
   else: key=base
   if any(not x for x in key): blank+=1; continue
   if key in seen: dupes+=1
   seen.add(key)
 print({"kind":kind,"rows":rows,"unique_keys":len(seen),"duplicate_keys":dupes,"blank_keys":blank,"sha256":file_sha256(path)})

if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('kind',choices=REQUIRED); p.add_argument('path',type=Path); a=p.parse_args(); run(a.kind,a.path)