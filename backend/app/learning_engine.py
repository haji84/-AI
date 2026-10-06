"""Bounded deterministic correction candidates; never overwrite official data."""
import hashlib
import json
import re

TEXT_TASKS={'ocr','proper_names','audio_correction','document_correction'}
LABEL_TASKS={'document_classification','facility_linking','photo_classification','workflow_pattern'}
TASKS=TEXT_TASKS|LABEL_TASKS
ENGINE='literal-correction-v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def compile_corrections(task,examples):
    if task not in TASKS:raise ValueError('unsupported learning task')
    entries={}
    for example in examples:
        if example['review_status']!='approved':continue
        before,after=example['input_text'],example['output_text']
        if not isinstance(before,str) or not before or not isinstance(after,str) or max(len(before),len(after))>2000:raise ValueError('invalid correction')
        if before in entries and entries[before]!=after:raise ValueError('conflicting approved corrections')
        entries[before]=after
    if len(entries)>500:raise ValueError('too many correction entries')
    return {'engine':ENGINE,'task':task,'entries':sorted(entries.items(),key=lambda item:(-len(item[0]),item[0]))}


def apply_artifact(artifact,input_text):
    if artifact.get('engine')!=ENGINE or artifact.get('task') not in TASKS:raise ValueError('unsupported artifact')
    if not isinstance(input_text,str) or len(input_text)>8000:raise ValueError('input too large')
    raw=artifact.get('entries')
    if not isinstance(raw,list) or len(raw)>500:raise ValueError('invalid artifact entries')
    entries={}
    for pair in raw:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or not isinstance(pair[0],str) or not pair[0] or not isinstance(pair[1],str) or max(map(len,pair))>2000:raise ValueError('invalid artifact entry')
        if pair[0] in entries:raise ValueError('duplicate artifact entry')
        entries[pair[0]]=pair[1]
    if artifact['task'] in LABEL_TASKS:
        output=entries.get(input_text,input_text)
    elif not entries:output=input_text
    else:
        pattern=re.compile('|'.join(re.escape(key) for key in sorted(entries,key=lambda value:(-len(value),value))))
        chunks=[];position=0;size=0
        for match in pattern.finditer(input_text):
            chunk=input_text[position:match.start()]+entries[match.group()];size+=len(chunk)
            if size>32000:raise ValueError('suggestion expansion exceeds bound')
            chunks.append(chunk);position=match.end()
        chunks.append(input_text[position:]);output=''.join(chunks)
        if len(output)>32000:raise ValueError('suggestion expansion exceeds bound')
    return {'original':input_text,'suggestion':output,'changed':input_text!=output,'human_review_required':True,'artifact_sha256':fingerprint(artifact),'engine':ENGINE}


def validate_cases(cases):
    if not isinstance(cases,list) or not 1<=len(cases)<=100:raise ValueError('fixed evaluation needs1..100 cases')
    seen=set()
    for case in cases:
        if not isinstance(case,dict) or set(case)!={'input','expected'} or any(not isinstance(case[key],str) or len(case[key])>4000 for key in case):raise ValueError('invalid fixed case')
        if case['input'] in seen:raise ValueError('duplicate fixed evaluation input')
        seen.add(case['input'])
    return cases


def compare_artifacts(champion,candidate,cases):
    validate_cases(cases)
    if champion['task']!=candidate['task']:raise ValueError('task mismatch')
    left=[];right=[]
    for case in cases:
        left.append(apply_artifact(champion,case['input'])['suggestion']==case['expected'])
        right.append(apply_artifact(candidate,case['input'])['suggestion']==case['expected'])
    n=len(cases)
    return {'metric':'exact-match-v1','case_count':n,'champion':{'correct':sum(left),'exact_accuracy':sum(left)/n},
        'candidate':{'correct':sum(right),'exact_accuracy':sum(right)/n},'no_regression':all(b>=a for a,b in zip(left,right)),
        'strict_improvement':sum(right)>sum(left),'champion_artifact_sha256':fingerprint(champion),'candidate_artifact_sha256':fingerprint(candidate),'evaluation_sha256':fingerprint(cases)}
