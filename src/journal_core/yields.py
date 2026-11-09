"""Reviewed food-specific cooking yields, saved privately.

Yield = grams in prepared state per gram raw purchase weight.
Do not use a generic yield or a yield for a different cooking method.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import math
import settings
from .grocery import product_name

STATES = {'cooked','drained','as_served'}


def yield_file() -> Path:
    return settings.JOURNAL_STATE_DIR / 'food_yields.json'


def load_yields(file: Path | None = None) -> dict[str, dict]:
    file = Path(file) if file else yield_file()
    if not file.exists(): return {}
    payload=json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(payload,dict) or payload.get('version')!=1:
        raise ValueError('Invalid cooking yield database')
    results={}
    for entry in payload.get('records',[]):
        row=validate_yield(entry)
        results[f"{row['product']}|{row['from_state']}"]=row
    return results


def validate_yield(entry:dict) -> dict:
    product=product_name(str(entry.get('product','')))
    state=str(entry.get('from_state',''))
    method=str(entry.get('method','')).strip()
    source=str(entry.get('source','')).strip()
    try: raw=float(entry.get('raw_grams')); prepared=float(entry.get('prepared_grams'))
    except (ValueError,TypeError): raise ValueError('Provide positive raw and prepared measured grams') from None
    if not product or len(product)>160 or state not in STATES or not method or not source or (
        not math.isfinite(raw) or not math.isfinite(prepared) or raw<=0 or prepared<=0 or raw>1e6 or prepared>1e6
    ):
        raise ValueError('Cooking yield requires a food, state, method, source and valid weights')
    # 0.05–8 is a guardrail, not an accepted cooking-yield claim.
    factor=prepared/raw
    if not 0.05<=factor<=8:
        raise ValueError('Conversion outside plausible application bounds; review your measurements')
    return {'product':product,'from_state':state,'raw_grams':raw,
            'prepared_grams':prepared,'method':method,'source':source,
            'factor':factor,'saved_at':str(entry.get('saved_at',''))}


def save_yield(entry:dict,file:Path|None=None) -> dict:
    file=Path(file) if file else yield_file()
    row=validate_yield(entry)
    row['saved_at']=datetime.now(timezone.utc).isoformat()
    records=load_yields(file)
    records[f"{row['product']}|{row['from_state']}"]=row
    file.parent.mkdir(parents=True,exist_ok=True)
    tmp=file.with_suffix('.tmp')
    try:
        tmp.write_text(json.dumps({'version':1,'records':list(records.values())},ensure_ascii=False,indent=2),encoding='utf-8')
        os.chmod(tmp,0o600)
        os.replace(tmp,file)
    finally: tmp.unlink(missing_ok=True)
    return row


def purchase_raw(prepared_grams:float,record:dict) -> float:
    """raw = prepared / (prepared_grams_per_raw_gram), not reciprocal."""
    row=validate_yield(record)
    if prepared_grams<0 or not math.isfinite(prepared_grams):raise ValueError('Bad prepared weight')
    return prepared_grams/row['factor']
