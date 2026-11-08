"""USDA FoodData Central: explicit, reviewed mappings; never auto-match recipe names.

Credentials stay in FDC_API_KEY environment variable. Nothing fetched at import time.
Only unbranded datasets with per-100g nutrient amounts are supported here.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .nutrition import key

API = 'https://api.nal.usda.gov/fdc/v1'
SUPPORTED = {'Foundation', 'SR Legacy'}
NUTRIENTS = {'protein_g': 1003, 'carbs_g': 1005, 'fat_g': 1004}
FIELDS = ('ingredient','measurement_state','basis_unit','kcal','protein_g','carbs_g','fat_g','source')


def _get(endpoint: str, params: dict, api_key: str | None = None) -> dict:
    api_key = api_key or os.environ.get('FDC_API_KEY')
    if not api_key:
        raise ValueError('Set FDC_API_KEY in .env (never commit the API key).')
    url = f'{API}/{endpoint}?{urlencode({**params, "api_key": api_key})}'
    req = Request(url, headers={'User-Agent': 'CrewAI-Journal-nutrition/0.3 (local personal app)'})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except HTTPError as exc:
        raise ValueError(f'FoodData Central HTTP error {exc.code}. Check API key, rate limit and FDC ID.') from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError('FoodData Central connection or response error; no data saved.') from exc


def search(query: str, *, limit: int = 12, api_key: str | None = None) -> list[dict]:
    if not query.strip():
        raise ValueError('Search query cannot be empty')
    if not 1 <= limit <= 25:
        raise ValueError('Limit must be between 1 and 25')
    api_key = api_key or os.environ.get('FDC_API_KEY')
    if not api_key:
        raise ValueError('Set FDC_API_KEY in .env (never commit it)')
    req = Request(f'{API}/foods/search?{urlencode({"api_key": api_key})}',
                  data=json.dumps({'query':query,'pageSize':limit,
                                   'dataType':['Foundation','SR Legacy']}).encode('utf-8'),
                  headers={'User-Agent':'CrewAI-Journal-nutrition/0.3',
                           'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=15) as resp:
            response=json.load(resp)
    except HTTPError as exc:
        raise ValueError(f'FoodData Central HTTP {exc.code}; check API key and rate limits') from exc
    except (URLError,TimeoutError,json.JSONDecodeError) as exc:
        raise ValueError('FoodData Central search connection/response error; no data saved') from exc
    return [{'fdc_id': f.get('fdcId'), 'description': f.get('description'),
             'data_type': f.get('dataType'), 'publication_date': f.get('publicationDate')}
            for f in response.get('foods', []) if f.get('dataType') in SUPPORTED]


def fetch(fdc_id: int, *, api_key: str | None = None) -> dict:
    if not 1 <= fdc_id <= 999999999:
        raise ValueError('Invalid FDC ID')
    return _get(f'food/{fdc_id}', {}, api_key)


def food_to_row(food: dict, *, ingredient: str, state: str) -> dict:
    """Only verified source records, complete per-100g macros, exact explicit mapping.

    Retain source ID and description so reviewers can audit ingredient choice.
    """
    if food.get('dataType') not in SUPPORTED:
        raise ValueError('Only USDA Foundation and SR Legacy records supported; branded serving bases require separate verification')
    if state not in {'raw', 'cooked', 'drained', 'as_served'}:
        raise ValueError('Invalid measurement state')
    if not ingredient.strip():
        raise ValueError('Ingredient name required')
    fdc_id = food.get('fdcId')
    if not isinstance(fdc_id, int):
        raise ValueError('Missing FoodData Central ID')
    values = {}
    for entry in food.get('foodNutrients', []):
        nutrient = entry.get('nutrient') or {}
        nid = nutrient.get('id')
        amount = entry.get('amount')
        if not isinstance(amount, (float, int)) or amount < 0:
            continue
        if nid in (1003,1004,1005) and str(nutrient.get('unitName','')).lower() == 'g':
            values[nid] = float(amount)
        if nid in (1008,2047,2048) and str(nutrient.get('unitName','')).lower() == 'kcal':
            values[nid] = float(amount)
    energy = next((values[id] for id in (2047,2048,1008) if id in values), None)
    if energy is None or any(n not in values for n in NUTRIENTS.values()):
        raise ValueError('Food record lacks complete kcal/protein/carbohydrate/fat per 100g; no entry created')
    return {'ingredient': key(ingredient), 'measurement_state':state,'basis_unit':'g',
            'kcal':energy, **{field:values[nid] for field,nid in NUTRIENTS.items()},
            'source':f'USDA_FDC:{fdc_id} ({food.get("dataType")}; {food.get("description", "")}; checked manually)'}


def write_reference(path: Path, row: dict, *, replace: bool = False) -> None:
    """Write a private reference atomically. Never quietly overwrite a mapping."""
    path = Path(path)
    if path.exists():
        with path.open(encoding='utf-8-sig', newline='') as f:
            current = list(csv.DictReader(f))
    else:
        current = []
    if not str(row.get('source', '')).startswith(('USDA_FDC:', 'LABEL:')):
        raise ValueError('Only explicitly selected USDA records or user-verified labels are supported')
    same = [r for r in current if key(r['ingredient']) == key(row['ingredient']) and
            r['measurement_state'] == row['measurement_state']]
    if same and not replace:
        raise ValueError('Mapping already exists. Use --replace only after reviewing the record.')
    updated = [r for r in current if (key(r['ingredient']),r['measurement_state']) !=
               (key(row['ingredient']),row['measurement_state'])]
    updated.append({name:str(row[name]) for name in FIELDS})
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + '.tmp')
    try:
        with staging.open('w', encoding='utf-8', newline='') as file:
            writer=csv.DictWriter(file,fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sorted(updated,key=lambda x:(x['ingredient'],x['measurement_state'])))
        os.chmod(staging, 0o600)
        os.replace(staging,path)
    finally:
        staging.unlink(missing_ok=True)


def label_to_row(*,ingredient:str,state:str,basis_unit:str,kcal:float,protein_g:float,carbs_g:float,fat_g:float,label_id:str)->dict:
    """Local commercial nutrition label: user confirms numbers per 100g or 100ml."""
    if not ingredient.strip() or state not in {'raw','cooked','drained','as_served'} or basis_unit not in {'g','ml'}:
        raise ValueError('Specify ingredient, preparation state and g/ml basis')
    if len(label_id.strip())<4:
        raise ValueError('Provide identifiable brand/product or barcode')
    nums=(kcal,protein_g,carbs_g,fat_g)
    if any(not isinstance(x,(int,float)) or x<0 or x>1500 for x in nums):
        raise ValueError('Nutrition numbers must be nonnegative per 100g/ml')
    if abs(protein_g*4+carbs_g*4+fat_g*9-kcal)>max(120,0.35*kcal):
        raise ValueError('Label energy appears inconsistent with macros; check units')
    return {'ingredient':key(ingredient),'measurement_state':state,'basis_unit':basis_unit,
            'kcal':kcal,'protein_g':protein_g,'carbs_g':carbs_g,'fat_g':fat_g,
            'source':f'LABEL:{label_id.strip()} (entered and checked by user)'}
