"""Explicit user resolution for ambiguous shopping ingredients; state is private and local."""
from __future__ import annotations
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from .nutrition import key
import settings

STATES={'raw','cooked','drained','as_served'}
UNITS={'g','kg','ml','l','item','un'}


def review_id(day:int|None, recipe:str, person:str, raw:str) -> str:
    value=json.dumps([day,recipe,person,raw],ensure_ascii=False)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]


def group_review_id(raw: str) -> str:
    """One decision for the same ingredient expression throughout a week.

    Quantities are intentionally removed so 100 g tomato/spinach and 140 g
    tomato/spinach can share a *choice* but keep their own source amounts.
    """
    import re
    text = re.sub(r'^\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l|un\.?|unidades?)?\s*', '', raw, flags=re.I)
    text = key(text)
    return hashlib.sha256(('group-v04:'+text).encode('utf-8')).hexdigest()[:16]


def review_file(week_start:str)->Path:
    d=date.fromisoformat(week_start)
    if d.weekday()!=0:
        raise ValueError('Expected Monday week start')
    return settings.JOURNAL_STATE_DIR / 'shopping_reviews' / f'{d.isoformat()}.json'


def validate_resolution(resolution:dict)->dict:
    action=resolution.get('action','pending')
    if action not in {'pending','skip','replace','choose','split'}:
        raise ValueError('Shopping decision must be pending, skip, choose or replace')
    if action=='split':
        parts=resolution.get('parts')
        if not isinstance(parts,list) or not 2<=len(parts)<=6:
            raise ValueError('Split requires two to six named ingredients')
        result=[]
        for part in parts:
            name=key(str(part.get('name','')))
            try: percent=float(part.get('percent'))
            except (TypeError,ValueError): raise ValueError('Each split needs a numeric percentage') from None
            if not name or '/' in name or len(name)>160 or not 0<percent<=100:
                raise ValueError('Each split must have one ingredient and a percentage above zero')
            result.append({'name':name,'percent':percent})
        if len({p['name'] for p in result})!=len(result):
            raise ValueError('Split ingredient names must be distinct')
        if abs(sum(p['percent'] for p in result)-100)>0.001:
            raise ValueError('Split percentages must total exactly 100%')
        return {'action':'split','parts':result}
    if action=='choose':
        name=key(str(resolution.get('name','')))
        if not name or '/' in name or len(name)>160:
            raise ValueError('Choose one exact ingredient name (no slash/alternatives)')
        return {'action':'choose','name':name}
    if action!='replace':
        return {'action':action}
    name=key(str(resolution.get('name','')))
    unit=str(resolution.get('unit','')).strip().lower()
    state=str(resolution.get('state','')).strip()
    try:
        qty=float(resolution.get('quantity'))
    except (TypeError,ValueError):
        raise ValueError('Replacement quantity must be a number') from None
    if not name or len(name)>160 or '/' in name or qty<=0 or qty>50000 or unit not in UNITS or state not in STATES:
        raise ValueError('Replacement needs one explicit ingredient, positive quantity, recognized unit and measurement state')
    return {'action':'replace','name':name,'quantity':qty,'unit':unit,'state':state}


def load_reviews(week_start:str)->dict[str,dict]:
    file=review_file(week_start)
    if not file.exists():
        return {}
    payload=json.loads(file.read_text(encoding='utf-8'))
    if payload.get('week_start')!=week_start or not isinstance(payload.get('resolutions'),dict):
        raise ValueError('Invalid shopping review file')
    return {rid:validate_resolution(row) for rid,row in payload['resolutions'].items()}


def save_reviews(week_start:str, rows:dict[str,dict])->Path:
    file=review_file(week_start)
    validated={k:validate_resolution(v) for k,v in rows.items()}
    if not all(len(k)==16 and all(c in '0123456789abcdef' for c in k) for k in validated):
        raise ValueError('Invalid review item identifier')
    file.parent.mkdir(parents=True,exist_ok=True)
    tmp=file.with_name(file.name+'.tmp')
    try:
        tmp.write_text(json.dumps({'week_start':week_start,'resolutions':validated},ensure_ascii=False,indent=2),encoding='utf-8')
        os.chmod(tmp,0o600)
        os.replace(tmp,file)
    finally:
        tmp.unlink(missing_ok=True)
    return file
