"""Conservative shopping consolidation with a practical German supermarket view.

Audit rows retain recipe source states; supermarket presentation groups equivalent
products without silently converting cooked to raw weights. Shopping decisions
are stored separately from the approved weekly menu.
"""
from __future__ import annotations
from collections import defaultdict
from csv import DictWriter
from io import StringIO
import re
from .recipe_parser import get_recipe
from .nutrition import key, reference_state
from .reviews import review_id, group_review_id, validate_resolution
from .grocery import SECTIONS, product_name, supermarket_rows
from .yields import load_yields


def _canonical_unit(quantity:float, unit:str|None)->tuple[float,str]|None:
    unit=(unit or '').lower()
    if unit in ('g','ml','item','un','unidade','unidades','unid.','unid'):
        return (quantity,'un' if unit not in ('g','ml') else unit)
    if unit=='kg': return quantity*1000,'g'
    if unit=='l': return quantity*1000,'ml'
    return None


def _reason(ing) -> str | None:
    if ing.optional: return 'Optional ingredient — include or skip'
    if ing.ambiguous or ing.quantity is None or 'chili pronto' in (ing.name or '').casefold():
        return 'Choose a specific ingredient or quantity'
    if ing.unit not in ('g','kg','ml','l','item','un','unidade','unidades','unid','unid.'):
        return 'Quantity unit needs review'
    return None


def _choices(raw: str) -> list[str]:
    """Suggest choices only for obvious alternatives; never infer compound recipes."""
    expression = re.sub(r'^\s*\d+(?:[.,]\d+)?\s*(?:g|kg|ml|l)?\s*', '', raw, flags=re.I)
    expression = re.sub(r'\s*\(opcional\).*$', '', expression, flags=re.I).strip()
    if '/' in expression:
        fragments=[x.strip() for x in expression.split('/')]
    elif re.search(r'\s+ou\s+',expression):
        fragments=re.split(r'\s+ou\s+',expression)
    elif re.search(r'\s+e\s+',expression):
        fragments=re.split(r'\s+e\s+',expression)
    elif re.search(r'\bfruta\b',expression,re.I):
        fragments=['maçã','banana','laranja','pera']
    elif '(opcional)' in raw.casefold():
        fragments=[expression]
    else:
        fragments=[]
    return [key(s) for s in fragments if s and key(s)]


def review_kind(source, raw:str)->str:
    content=raw.casefold()
    if getattr(source,'optional',False):return 'optional'
    if source.quantity is None:return 'missing_quantity'
    if re.search(r'\bfruta\b',content):return 'fruit_choice'
    if 'chili pronto' in content:return 'prepared_dish'
    if ' ou ' in content:return 'alternative'
    if '/' in content or re.search(r'\b(?:pepino e folhas|limao e ervas|limão e ervas)\b',content):
        return 'mixed_ingredients'
    return 'ingredient_choice'


def shopping_list(menu,catalog,*,include_optional:bool=False,resolutions:dict[str,dict]|None=None)->dict:
    resolutions=resolutions or {}
    totals=defaultdict(float)
    sources=defaultdict(set)
    unresolved=[]
    reviewed=0

    def add(name,state,qty,unit,factor,recipe):
        group=(key(name),state,unit)
        totals[group]+=qty*factor
        sources[group].add(recipe)

    def issue(day,recipe,person,ingredient,source,reason,factor):
        nonlocal reviewed
        rid=review_id(day,recipe,person,ingredient)
        gid=group_review_id(ingredient)
        decision=validate_resolution(resolutions.get(rid, resolutions.get(gid,{'action':'pending'})))
        if decision['action']=='skip':
            reviewed+=1
            return
        if decision['action']=='choose':
            converted=_canonical_unit(source.quantity,source.unit) if source.quantity is not None else None
            if converted is not None:
                qty,unit=converted
                add(decision['name'],reference_state(recipe.split(':')[0],source),qty,unit,factor,recipe)
                reviewed+=1
                return
            reason+='; source quantity missing, use manual replacement'
        if decision['action']=='split':
            converted=_canonical_unit(source.quantity,source.unit) if source.quantity is not None else None
            if converted is not None:
                qty,unit=converted
                for part in decision['parts']:
                    add(part['name'],reference_state(recipe.split(':')[0],source),
                        qty*part['percent']/100,unit,factor,recipe)
                reviewed+=1
                return
            reason+='; source quantity missing, enter explicit quantities'
        if decision['action']=='replace':
            canonical=_canonical_unit(decision['quantity'],decision['unit'])
            if canonical is None: raise ValueError('Invalid replacement unit')
            qty,unit=canonical
            add(decision['name'],decision['state'],qty,unit,factor,recipe)
            reviewed+=1
            return
        unresolved.append({'review_id':rid,'group_id':gid,'day':day,'recipe':recipe,'person':person,
                          'ingredient':ingredient,'reason':reason,'decision':'pending',
                          'choices':_choices(ingredient), 'kind':review_kind(source,ingredient),
                          'source_quantity':source.quantity,'source_unit':source.unit})

    for category,recipe_ids in menu.selections.items():
        for index,recipe_id in enumerate(recipe_ids):
            recipe=get_recipe(catalog,recipe_id)
            for person in ('person_a','person_b'):
                factor=menu.portion_factors.get(person,1.0)
                for ing in recipe.ingredients[person]:
                    # 'frango cozido/desfiado' is a single food/preparation, not a choice.
                    desc=key(ing.name or '')
                    if desc in {'frango /desfiado','frango/desfiado','frango cozido/desfiado'}:
                        converted=_canonical_unit(ing.quantity,ing.unit) if ing.quantity is not None else None
                        if converted:
                            q,u=converted
                            add('frango','cooked',q,u,factor,recipe.id)
                            continue
                    reason=_reason(ing)
                    if reason:
                        if ing.optional and include_optional:
                            reason=None
                        else:
                            issue(index+1,recipe.id,person,ing.raw,ing,reason,factor)
                            continue
                    converted=_canonical_unit(ing.quantity,ing.unit)
                    if converted is None:
                        issue(index+1,recipe.id,person,ing.raw,ing,'Unrecognized unit',factor)
                        continue
                    qty,unit=converted
                    norm=key(ing.name or '')
                    if not norm or norm.startswith('('):
                        issue(index+1,recipe.id,person,ing.raw,ing,'Unknown ingredient name',factor)
                        continue
                    # Fractional unit portions are NOT purchase errors. Round after adding
                    # all uses across the week. Source portions stay unchanged.
                    add(norm,reference_state(category,ing),qty,unit,factor,recipe.id)

    add('leite (cafe)','as_served',700,'ml',1.0,'breakfast:global_rule')
    class Coffee:
        quantity=None
        unit=None
    issue(None,'breakfast:global_rule','both','Coffee grounds, amount not specified',Coffee(),
          'Coffee grounds unspecified: enter an amount or skip if pantry-stocked',1.0)

    items=[{'ingredient':name,'state':state,'unit':unit,'quantity':round(qty,2),
            'recipes':', '.join(sorted(sources[(name,state,unit)]))}
           for (name,state,unit),qty in sorted(totals.items())]

    # Create a market-facing representation independent of audit ingredient lines.
    grouped_items=[]
    for item in items:
        copied=item.copy()
        copied['ingredient']=product_name(item['ingredient'])
        grouped_items.append(copied)
    market=supermarket_rows(grouped_items,yields=load_yields())

    # Group repeated review prompts across people and days. Keep original entries
    # available for audit, but the interface should show only review_groups.
    groups={}
    for record in unresolved:
        gid=record['group_id']
        obj=groups.setdefault(gid,{'group_id':gid,'ingredient':record['ingredient'],
                                   'reason':record['reason'],'choices':record['choices'],
                                   'kind':record['kind'],
                                   'count':0,'recipes':set(),'examples':[],
                                   'can_choose':True})
        obj['count']+=1
        obj['recipes'].add(record['recipe'])
        if len(obj['examples'])<2:obj['examples'].append(record['ingredient'])
        if record['source_quantity'] is None or _canonical_unit(record['source_quantity'],record['source_unit']) is None:
            obj['can_choose']=False
    reviews=[{**g,'recipes':', '.join(sorted(g['recipes']))} for g in groups.values()]
    reviews.sort(key=lambda g:(g['reason'],g['ingredient'].casefold()))
    conversion_count=sum(1 for r in market if r['requires_conversion'])
    return {'week_start':menu.week_start,'items':items,'supermarket':market,
            'needs_review':unresolved,'review_groups':reviews,
            'reviewed':reviewed,'shopping_ready':not unresolved and not conversion_count,
            'conversion_count':conversion_count,
            'conversion_needed':[row for row in market if row['requires_conversion']],
            'warning':'Ambiguous ingredients and cooked/raw purchase conversions must be reviewed. Source recipe amounts are not modified.'}


def as_markdown(result:dict)->str:
    out=[f'# Shopping list / Einkaufsliste — Woche ab {result["week_start"]}','',
         '> GEPRÜFT' if result['shopping_ready'] else '> ENTWURF — vor dem Einkauf prüfen',
         '', 'Mengen für beide Personen. Stückzahlen sind beim Einkauf aufgerundet; Rezeptportionen bleiben unverändert.', '']
    rows=result.get('supermarket')
    if rows is None: rows=supermarket_rows([{**r,'ingredient':product_name(r['ingredient'])} for r in result['items']])
    for section in SECTIONS:
        entries=[r for r in rows if r['section']==section]
        if not entries: continue
        out += [f'## {section}','']
        for r in entries:
            detail=f' — ⚠️ {r["note"]}' if r['note'] else ''
            out.append(f'- [ ] **{r["label"]}** — {r["quantity_display"]}{detail}')
        out.append('')
    reviews=result.get('review_groups',[])
    if reviews:
        out += ['## Offene Entscheidungen / Needs review','']
        for r in reviews:
            out.append(f'- [ ] {r["ingredient"]} — {r["reason"]} ({r["count"]}x; {r["recipes"]})')
        out.append('')
    elif result['needs_review']:
        out += ['## Needs review','']
        for r in result['needs_review']:
            out.append(f'- [ ] {r["ingredient"]} ({r["recipe"]}): {r["reason"]}')
        out.append('')
    out += ['## Hinweis','',result['warning'],'']
    return '\n'.join(out)


def as_csv(result:dict)->str:
    out=StringIO()
    columns=['section','ingredient','label','quantity_display','unit','quantity','note','recipes']
    writer=DictWriter(out,fieldnames=columns)
    writer.writeheader()
    rows=result.get('supermarket')
    if rows is None:
        rows=supermarket_rows([{**r,'ingredient':product_name(r['ingredient'])} for r in result['items']])
    for item in rows: writer.writerow({k:item.get(k,'') for k in columns})
    return out.getvalue()
