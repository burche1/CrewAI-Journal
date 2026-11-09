"""Conservative shopping consolidation with an explicit resolution workflow.

Recipe data and approved menu are never changed by shopping corrections.
"""
from __future__ import annotations
from collections import defaultdict
from csv import DictWriter
from io import StringIO
from .recipe_parser import get_recipe
from .nutrition import key, reference_state
from .reviews import review_id, validate_resolution


def _canonical_unit(quantity:float,unit:str|None)->tuple[float,str]|None:
    unit=(unit or '').lower()
    if unit in ('g','ml','item','un','unidade','unidades','unid.','unid'):
        return (quantity,'un' if unit not in ('g','ml') else unit)
    if unit=='kg': return quantity*1000,'g'
    if unit=='l': return quantity*1000,'ml'
    return None


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
        if unit=='un' and abs(qty*factor-round(qty*factor))>0.001:
            return 'Fractional purchase units after scaling; consider rounding'
        return None

    def issue(day,recipe,person,ingredient,reason):
        nonlocal reviewed
        rid=review_id(day,recipe,person,ingredient)
        decision=validate_resolution(resolutions.get(rid,{'action':'pending'}))
        if decision['action']=='skip':
            reviewed+=1
            return
        if decision['action']=='replace':
            canonical=_canonical_unit(decision['quantity'],decision['unit'])
            if canonical is None:
                raise ValueError('Invalid replacement unit')
            qty,unit=canonical
            # Global coffee line is already for both people / whole week; do not scale.
            factor=1.0 if day is None else menu.portion_factors.get(person,1.0)
            caution=add(decision['name'],decision['state'],qty,unit,factor,recipe)
            reviewed+=1
            if not caution: return
            reason=caution
        unresolved.append({'review_id':rid,'day':day,'recipe':recipe,'person':person,
                           'ingredient':ingredient,'reason':reason,'decision':decision['action']})

    for category,recipe_ids in menu.selections.items():
        for index,recipe_id in enumerate(recipe_ids):
            recipe=get_recipe(catalog,recipe_id)
            for person in ('person_a','person_b'):
                factor=menu.portion_factors.get(person,1.0)
                for ing in recipe.ingredients[person]:
                    if ing.optional and not include_optional:
                        issue(index+1,recipe.id,person,ing.raw,'Optional: choose inclusion or skip')
                        continue
                    if ing.ambiguous or ing.quantity is None or 'chili pronto' in (ing.name or '').casefold():
                        issue(index+1,recipe.id,person,ing.raw,'Ingredient choice or quantity needs review')
                        continue
                    converted=_canonical_unit(ing.quantity,ing.unit)
                    if converted is None:
                        issue(index+1,recipe.id,person,ing.raw,'Unrecognized unit; conversion not guessed')
                        continue
                    qty,unit=converted
                    norm=key(ing.name or '')
                    if not norm or norm.startswith('('):
                        issue(index+1,recipe.id,person,ing.raw,'Unrecognized ingredient name')
                        continue
                    state=reference_state(category,ing)
                    if unit=='un' and abs(qty*factor-round(qty*factor))>0.001:
                        issue(index+1,recipe.id,person,ing.raw,'Fractional purchase units after scaling; resolve to whole units')
                    else:
                        add(norm,state,qty,unit,factor,recipe.id)
    # Two people, seven breakfasts; 50 ml milk per person/day in source global rule.
    add('leite (cafe)','as_served',700,'ml',1.0,'breakfast:global_rule')
    issue(None,'breakfast:global_rule','both','Coffee, ~250–300 ml brewed per person each breakfast',
          'Coffee grounds quantity unspecified; choose an amount or skip')
    items=[{'ingredient':name,'state':state,'unit':unit,'quantity':round(qty,2),
            'recipes':', '.join(sorted(sources[(name,state,unit)]))}
           for (name,state,unit),qty in sorted(totals.items())]
    return {'week_start':menu.week_start,'items':items,'needs_review':unresolved,
            'reviewed':reviewed,'shopping_ready':not unresolved,
            'warning':'Verify raw/cooked conversions and recipe overlaps before shopping; cooked weights are not automatically converted to raw purchases.'}


def as_markdown(result:dict)->str:
    out=[f'# Shopping list — week of {result["week_start"]}','',
         '> REVIEWED' if result['shopping_ready'] else '> DRAFT — unresolved items remain; check before buying',
         '', '## Consolidated quantities','', '| Ingredient | Qty | State |','|---|---:|---|']
    for item in result['items']:
        out.append(f'| {item["ingredient"]} | {item["quantity"]:g} {item["unit"]} | {item["state"]} |')
    out +=['','## Needs review','']
    for r in result['needs_review']:
        out.append(f'- [ ] {r["ingredient"]} ({r["recipe"]}, {r["person"]}): {r["reason"]}')
    out+=['','## Caution',result['warning'],'']
    return '\n'.join(out)


def as_csv(result:dict)->str:
    out=StringIO()
    writer=DictWriter(out,fieldnames=['ingredient','quantity','unit','state','recipes'])
    writer.writeheader()
    writer.writerows(result['items'])
    return out.getvalue()
