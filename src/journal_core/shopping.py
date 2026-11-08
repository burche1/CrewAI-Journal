"""Consolidate unambiguous recipe quantities; preserve all unresolved items for review."""
from __future__ import annotations
from collections import defaultdict
from csv import DictWriter
from datetime import date, timedelta
from io import StringIO
from .recipe_parser import get_recipe
from .nutrition import key, reference_state


def _canonical_unit(quantity: float, unit: str | None) -> tuple[float,str] | None:
    unit = (unit or '').casefold()
    if unit in ('g','ml','item','unidade','unidades','unid.','unid'):
        return quantity, 'un' if unit in ('item','unidade','unidades','unid.','unid') else unit
    if unit == 'kg':
        return quantity*1000,'g'
    if unit == 'l':
        return quantity*1000,'ml'
    return None


def shopping_list(menu, catalog, *, include_optional:bool=False) -> dict:
    totals: dict[tuple[str,str,str],float] = defaultdict(float)
    sources: dict[tuple[str,str,str],set[str]] = defaultdict(set)
    unresolved=[]
    for category, recipe_ids in menu.selections.items():
        for day_index, recipe_id in enumerate(recipe_ids):
            recipe = get_recipe(catalog,recipe_id)
            for person in ('person_a','person_b'):
                factor = menu.portion_factors.get(person,1.0)
                for ing in recipe.ingredients[person]:
                    if ing.optional and not include_optional:
                        unresolved.append({'day':day_index+1,'recipe':recipe.id,'person':person,
                                'ingredient':ing.raw,'reason':'Optional: excluded from totals; choose whether to buy'})
                        continue
                    if ing.ambiguous or ing.quantity is None or 'chili pronto' in (ing.name or '').casefold():
                        unresolved.append({'day':day_index+1,'recipe':recipe.id,'person':person,
                                'ingredient':ing.raw,'reason':'Ingredient choice or quantity needs review'})
                        continue
                    converted = _canonical_unit(ing.quantity,ing.unit)
                    if converted is None:
                        unresolved.append({'day':day_index+1,'recipe':recipe.id,'person':person,
                                'ingredient':ing.raw,'reason':'Unrecognized unit; conversion deliberately not guessed'})
                        continue
                    qty,unit = converted
                    measurement = reference_state(category,ing)
                    norm = key(ing.name or '')
                    if not norm or norm.startswith('('):
                        unresolved.append({'day':day_index+1,'recipe':recipe.id,'person':person,
                                'ingredient':ing.raw,'reason':'Unrecognized ingredient name'})
                        continue
                    group=(norm,measurement,unit)
                    if unit == 'un' and abs((qty*factor)-round(qty*factor))>0.001:
                        unresolved.append({'day':day_index+1,'recipe':recipe.id,'person':person,
                            'ingredient':ing.raw,'reason':f'Portion scaling produced {qty*factor:.2f} pieces; round to purchasable whole units after review'})
                    totals[group] += qty*factor
                    sources[group].add(recipe.id)
    # Breakfast.md states 50 ml milk PER PERSON per breakfast in coffee, additional
    # to recipe portions. Include for the seven planned breakfasts.
    totals[('leite (cafe)','as_served','ml')] += 50 * 7 * 2
    sources[('leite (cafe)','as_served','ml')].add('breakfast:global_rule')
    unresolved.append({'day':None,'recipe':'breakfast:global_rule','person':'both',
        'ingredient':'Coffee, ~250–300 ml brewed per person each breakfast',
        'reason':'Beans/ground coffee quantity unspecified in source; add manually'})
    items=[{'ingredient':name,'state':state,'unit':unit,'quantity':round(quantity,2),
            'recipes':', '.join(sorted(sources[(name,state,unit)]))}
            for (name,state,unit),quantity in sorted(totals.items())]
    return {'week_start':menu.week_start,'items':items,'needs_review':unresolved,
            'warning':'Cooked and raw weights are kept separate; do NOT combine them as purchase amounts without a verified yield factor. Review all alternatives, optional items, and possible ingredient synonyms.'}


def as_markdown(result:dict) -> str:
    out=[f"# Shopping list — week of {result['week_start']}",'',
         '> Quantity groups are preliminary. Cooked and raw are separate. Resolve the review section before shopping.','',
         '## Consolidated quantities','', '| Ingredient | Qty | State |', '|---|---:|---|']
    for item in result['items']:
        out.append(f"| {item['ingredient']} | {item['quantity']:g} {item['unit']} | {item['state']} |")
    out += ['', '## Needs review', '']
    for row in result['needs_review']:
        out.append(f"- [ ] {row['ingredient']} ({row['recipe']}, {row['person']}): {row['reason']}")
    out += ['', '## Caution', result['warning'], '']
    return '\n'.join(out)


def as_csv(result:dict) -> str:
    file = StringIO()
    writer=DictWriter(file, fieldnames=['ingredient','quantity','unit','state','recipes'])
    writer.writeheader()
    for item in result['items']:
        writer.writerow(item)
    return file.getvalue()
