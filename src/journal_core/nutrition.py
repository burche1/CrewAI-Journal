"""Reviewable nutrition *subtotals*. Never mistake partial matches for daily macros.

Starter figures are generic demonstration estimates; users can provide verified per-100g
CSV from a nutritional authority or package labels. No silent unit conversions.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from .models import Recipe
from .recipe_parser import get_recipe

STARTER_REFERENCE = Path(__file__).resolve().parents[2] / 'config' / 'nutrition_reference_starter.csv'
DEFAULT_REFERENCE = None


def normalize(name: str) -> str:
    name = unicodedata.normalize('NFKD', name.casefold())
    name = ''.join(x for x in name if not unicodedata.combining(x))
    name = re.sub(r'\b(cru|crua|crus|cruas|cozido|cozida|cozidos|cozidas|escorrido|escorrida|seco|seca)\b', '', name)
    name = re.sub(r'\s+', ' ', name).strip(' .,')
    return name

ALIASES = {
    'ovos': 'ovo', 'ovo': 'ovo', 'batatas': 'batata', 'banana': 'banana',
    'aveia': 'aveia', 'skyr': 'skyr', 'frango': 'frango', 'peito de frango': 'frango',
    'arroz': 'arroz', 'pao integral': 'pao integral', 'macas': 'maca',
    'azeite': 'azeite', 'leite': 'leite', 'whey': 'whey', 'tomate': 'tomate',
    'frutas vermelhas': 'frutas vermelhas', 'feijao vermelho': 'feijao',
    'atum': 'atum', 'iogurte natural': 'iogurte natural',
}


def key(name: str) -> str:
    norm = normalize(name)
    return ALIASES.get(norm, norm)


def reference_file() -> Path:
    import settings
    return settings.configured_path('NUTRITION_REFERENCE_FILE', settings.JOURNAL_STATE_DIR / 'verified_nutrition.csv')


def load_reference(path: Path | None = None) -> dict[tuple[str, str], dict]:
    require_verified = path is None
    path = path or reference_file()
    rows = {}
    if not path.is_file():
        raise FileNotFoundError(f'Verified nutrition reference not yet available: {path}. Import reviewed USDA records or labels first.')
    with path.open(encoding='utf-8-sig', newline='') as file:
        for row in csv.DictReader(file):
            if require_verified and not (row.get('source') or '').startswith(('USDA_FDC:', 'LABEL:')):
                raise ValueError('Nutrition reference includes unverified/demo sources. Use only reviewed USDA or product-label mappings.')
            name = key(row['ingredient'])
            measurement = row.get('measurement_state','as_served').strip()
            if measurement not in {'raw','cooked','drained','as_served'}:
                raise ValueError(f'Invalid measurement state in nutrition data: {measurement}')
            basis_unit = (row.get('basis_unit') or 'g').strip().casefold()
            if basis_unit not in {'g','ml'}:
                raise ValueError(f'Invalid reference basis unit: {basis_unit}')
            obj = {'source': row.get('source','unverified'), 'name': name, 'basis_unit': basis_unit}
            for col in ('kcal','protein_g','carbs_g','fat_g'):
                value = float(row[col])
                if value < 0:
                    raise ValueError(f'Negative nutrition reference: {name}/{col}')
                obj[col] = value
            if (name,measurement) in rows:
                raise ValueError(f'Duplicate nutrition reference for {name}: {measurement}')
            rows[name,measurement] = obj
    return rows


def _quantity_g(ingredient) -> float | None:
    if ingredient.quantity is None or ingredient.unit is None:
        return None
    unit = ingredient.unit.casefold()
    if unit in ('g','ml'):
        # Milliliters cannot be treated as grams without food-specific density.
        return ingredient.quantity if unit == 'g' else None
    if unit == 'kg':
        return ingredient.quantity * 1000
    # Avoid converting eggs, pieces, fruit, scoop sizes, volumes to g by assumption.
    return None


def reference_state(category: str, ingredient) -> str:
    if ingredient.measurement_state != 'unknown':
        return ingredient.measurement_state
    name = key(ingredient.name or '')
    if category == 'dinner':
        return 'raw'
    if category == 'lunch' and name in {'arroz','massa','cuscuz','quinoa','lentilha','batata','frango','carne moida'}:
        return 'cooked'
    return 'as_served'


def recipe_nutrition(recipe: Recipe, person: str, scale: float=1.0, reference=None) -> dict:
    if person not in {'person_a','person_b'}:
        raise ValueError('Person must be person_a or person_b')
    if not 0.5 <= scale <= 2.0:
        raise ValueError('Portion scale must be between 0.5 and 2.0')
    reference = load_reference() if reference is None else reference
    totals = {x: 0.0 for x in ('kcal','protein_g','carbs_g','fat_g')}
    issues = []
    eligible = 0
    matched = 0
    for item in recipe.ingredients[person]:
        eligible += 1
        state = reference_state(recipe.category, item)
        entry = reference.get((key(item.name or ''),state))
        if item.optional or item.ambiguous or item.quantity is None:
            issues.append({'ingredient': item.raw, 'reason': 'optional / alternative / missing quantity'})
            continue
        if not entry:
            issues.append({'ingredient': item.raw, 'reason': f'No exact nutrition reference match for {key(item.name or "")} ({state})'})
            continue
        unit = (item.unit or '').lower()
        if unit == entry['basis_unit']:
            amount=item.quantity
        elif unit=='kg' and entry['basis_unit']=='g':
            amount=item.quantity*1000
        elif unit=='l' and entry['basis_unit']=='ml':
            amount=item.quantity*1000
        else:
            issues.append({'ingredient': item.raw, 'reason': f'Unit {unit} cannot safely convert to reference basis {entry["basis_unit"]}'})
            continue
        matched += 1
        for col in totals:
            totals[col] += entry[col] * amount * scale / 100
    return {
        'recipe_id': recipe.id, 'person': person, 'portion_factor': scale,
        'matched_items': matched, 'total_items': eligible,
        'coverage_items': round(matched / eligible, 3) if eligible else 0,
        'known_subtotal': {col: round(x, 1) for col,x in totals.items()},
        'complete': matched == eligible and bool(eligible), 'unresolved': issues,
        'caution': 'PARTIAL ESTIMATE: only matched ingredient weights counted; missing food, coffee, oils, volume conversions and alternative ingredients can make totals understated.',
    }


def week_nutrition(menu, catalog: dict[str, list[Recipe]], reference=None) -> dict:
    reference = load_reference() if reference is None else reference
    result = {'week_start':menu.week_start, 'reference':str(reference_file()), 'days':[],
              'warning':'Known subtotals, NOT validated calorie or macro targets. Incomplete recipes must not drive automatic portion optimization.'}
    for index in range(7):
        entry = {'day_index':index, 'persons':{}}
        for person in ('person_a','person_b'):
            scale = menu.portion_factors.get(person,1.0)
            lines = [recipe_nutrition(get_recipe(catalog,menu.selections[category][index]), person,scale,reference)
                     for category in ('breakfast','lunch','dinner','snacks')]
            subtotals = {col:round(sum(x['known_subtotal'][col] for x in lines),1) for col in ('kcal','protein_g','carbs_g','fat_g')}
            # Global Breakfast.md rule: each breakfast includes 50 ml milk in coffee.
            milk = reference.get(('leite','as_served'))
            global_extras = []
            if milk and milk['basis_unit'] == 'ml':
                for col in subtotals:
                    subtotals[col] = round(subtotals[col] + milk[col]*50/100, 1)
                global_extras.append('Coffee milk: 50 ml/person/day, based on Breakfast.md global rule')
            else:
                global_extras.append('Coffee milk: 50 ml/person/day not counted (no compatible milk reference)')
            entry['persons'][person] = {'known_subtotal': subtotals,'complete':all(x['complete'] for x in lines) and bool(milk),
                'global_extras':global_extras,
                'matched_items':sum(x['matched_items'] for x in lines),
                'total_items':sum(x['total_items'] for x in lines),
                'meals':lines}
        result['days'].append(entry)
    return result
