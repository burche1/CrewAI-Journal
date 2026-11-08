"""Conservative, read-only portion proposals. No optimization on partial/unverified data."""
from __future__ import annotations
from itertools import product
from .nutrition import recipe_nutrition, load_reference, key
from .recipe_parser import get_recipe
from .profiles import MacroTarget

FIELDS=('kcal','protein_g','carbs_g','fat_g')


def propose_day(menu,catalog,index:int,person:str,target:MacroTarget,*,reference=None)->dict:
    """Try bounded factors per meal; return suggestion, NOT an approved menu edit.

    Strictly requires all four meals complete and verified; breakfast coffee milk
    omitted here, so no automatic optimization unless supplied separately.
    """
    if not 0<=index<7 or person not in ('person_a','person_b'):
        raise ValueError('Invalid day or person')
    ref=load_reference() if reference is None else reference
    source_errors=[f'{name} ({state})' for (name,state),rec in ref.items()
                   if not str(rec.get('source','')).startswith(('USDA_FDC:', 'LABEL:'))]
    if source_errors:
        return {'status':'blocked','reason':'The reference contains unverified/demo rows; only reviewed USDA or label mappings are accepted.',
                'unverified_count':len(source_errors)}
    parts=[]
    missing=[]
    for category in ('breakfast','lunch','dinner','snacks'):
        recipe=get_recipe(catalog,menu.selections[category][index])
        data=recipe_nutrition(recipe,person,scale=getattr(menu,'portion_factors',{}).get(person,1.0),reference=ref)
        if not data['complete']:
            missing.append({'category':category,'recipe':recipe.id,'issues':data['unresolved']})
        parts.append(data['known_subtotal'])
    # Breakfast coffee milk MUST be included before optimizing, or block.
    if ('leite','as_served') not in ref or ref[('leite','as_served')]['basis_unit']!='ml':
        missing.append({'category':'breakfast','recipe':'coffee_milk','issues':['Milk volume requires verified ml reference']})
    if missing:
        return {'status':'blocked','reason':'Incomplete nutritional coverage; cannot safely optimize portions.',
                'missing':missing}
    milk=ref[('leite','as_served')]
    extras={field:milk[field]*0.5 for field in FIELDS}
    desired=target.model_dump()
    candidate_factors=(0.85,0.95,1.0,1.05,1.15)
    best=None
    for factors in product(candidate_factors,repeat=4):
        total={field:sum(factors[i]*parts[i][field] for i in range(4))+extras[field] for field in FIELDS}
        loss=sum((total[field]-desired[field])**2/max(desired[field],1.0)**2 * weight
                 for field,weight in [('kcal',2.0),('protein_g',2.0),('carbs_g',1.5),('fat_g',0.8)])
        loss+=0.25*sum((factor-1.0)**2 for factor in factors)
        if best is None or loss<best[0]:
            best=(loss,factors,total)
    return {'status':'suggestion_only', 'person':person,'day_index':index,
            'meal_multipliers_relative_to_approved_portions':dict(zip(('breakfast','lunch','dinner','snacks'),best[1])),
            'estimated_totals':{k:round(v,1) for k,v in best[2].items()},
            'targets':desired,'caution':'Read-only suggestion within ±15% per meal; review adequacy, ingredients and digestion. Never automatically change an approved plan.'}
