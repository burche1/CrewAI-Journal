"""Conservative grocery naming, aisle ordering and source-state notes for Germany.

This is an editorial shopping aid, not a nutrient or cooked/raw conversion engine.
Maintain one explicit alias dictionary so newly added recipes remain scalable.
"""
from __future__ import annotations
from collections import defaultdict
from math import ceil
import re
from .nutrition import key

SECTIONS = (
    'Obst & Gemüse',
    'Brot & Backwaren',
    'Fleisch & Fisch',
    'Käse, Eier & Molkerei',
    'Tiefkühlkost',
    'Reis, Nudeln & Getreide',
    'Konserven & Hülsenfrüchte',
    'Öle, Gewürze & Backzutaten',
    'Aufstriche, Snacks & Süßes',
    'Getränke',
    'Sonstiges / Prüfen',
)

# Every synonym below is deliberately explicit, not a fuzzy language-model guess.
ALIASES = {
    'leite (cafe)': 'leite', 'leite para cafe': 'leite',
    'file de salmao': 'salmao', 'file de salmão': 'salmao',
    'frango fatiado': 'frango', 'frango desfiado': 'frango',
    'frango cozido/desfiado': 'frango',
    'carne bovina para ensopado': 'carne para ensopado',
    'carne de vaca para ensopado': 'carne para ensopado',
    'espaguete integral seco': 'espaguete integral',
    'mozzarella': 'mussarela',
    'batatas': 'batata', 'ovos': 'ovo', 'macas': 'maca',
}

# These products are purchased in the same form whether a recipe labels them
# 'raw' or 'as_served'. Do NOT apply this to cooked grains, meat or vegetables.
PURCHASE_STABLE = {
    'azeite', 'leite', 'skyr', 'cottage', 'frischkase', 'frischkäse',
    'pesto', 'passata', 'tomate triturado', 'queijo', 'queijo ralado',
    'parmesao', 'feta', 'ricota', 'iogurte natural', 'mel',
    'geleia', 'pasta de amendoim', 'muesli', 'cornflakes',
}

LABELS = {
    'ovo':'Ovos', 'maca':'Maçãs', 'laranja':'Laranjas',
    'banana':'Bananas', 'leite':'Leite (incluindo café)',
    'azeite':'Azeite de oliva', 'salmao':'Salmão (filé)',
    'frango':'Frango', 'batata':'Batatas', 'arroz':'Arroz',
    'tomate':'Tomates', 'brocolis':'Brócolis', 'abobrinha':'Abobrinha',
    'pao integral':'Pão integral', 'queijo':'Queijo',
    'queijo ralado':'Queijo ralado', 'skyr':'Skyr',
    'frutas vermelhas':'Frutas vermelhas',
}

# Explicit ingredient memberships, expanded over time as new recipes are added.
AISLE_EXACT = {
    'Obst & Gemüse': {
        'abacate','abobrinha','banana','batata','brocolis','cenoura','cebola',
        'espinafre','laranja','limao','maca','pepino','pimentao','tomate',
        'tomate-cereja','frutas vermelhas','folhas','alface','alho',
    },
    'Brot & Backwaren': {
        'pao integral','pao branco','pao de forma','pao de forma branco',
        'wrap integral','wrap','tortilha','bagel','pita','bolachas de arroz',
    },
    'Fleisch & Fisch': {
        'frango','carne moida magra','carne para ensopado','peru moido',
        'salmao','atum fresco','peito de frango','peixe','carne bovina',
        'tofu firme',
    },
    'Käse, Eier & Molkerei': {
        'leite','ovo','skyr','iogurte natural','iogurte grego natural',
        'cottage','frischkase','feta','ricota','parmesao',
        'queijo','queijo ralado','mussarela','quark',
    },
    'Tiefkühlkost': {'frutas vermelhas congeladas','vegetais congelados'},
    'Reis, Nudeln & Getreide': {
        'arroz','arroz basmati','aveia','cuscuz','espaguete integral',
        'massa integral','lentilhas secas','lentilhas vermelhas secas',
        'quinoa','muesli','cornflakes','folhas de lasanha secas',
    },
    'Konserven & Hülsenfrüchte': {
        'feijao','feijao preto','grao-de-bico','milho','passata','tomate triturado',
        'atum','sardinha',
    },
    'Öle, Gewürze & Backzutaten': {
        'azeite','canela','chia','oleo de coco','fermento','farinha',
        'sal','pimenta','paprica','molho de soja',
    },
    'Aufstriche, Snacks & Süßes': {
        'geleia','mel','pasta de amendoim','pesto','nozes','hummus','whey',
    },
    'Getränke': {'cafe','cha','agua','suco'},
}


def product_name(value: str) -> str:
    normalized = key(value)
    return ALIASES.get(normalized, normalized)


def product_label(value: str) -> str:
    return LABELS.get(value, value[:1].upper()+value[1:])


def section_for(name: str) -> str:
    for section in SECTIONS:
        if name in AISLE_EXACT.get(section, ()): return section
    # Prefix fallback is just an aisle suggestion, never a product merge.
    if re.search(r'\b(frango|peru|salmao|carne)\b', name): return 'Fleisch & Fisch'
    if re.search(r'\b(brocolis|batata|pimentao|abobrinha|tomate|cebola|cenoura)\b', name): return 'Obst & Gemüse'
    if re.search(r'\b(queijo|leite|iogurte|skyr|cottage|ovo)\b', name): return 'Käse, Eier & Molkerei'
    if re.search(r'\b(arroz|massa|espaguete|cuscuz|quinoa|aveia)\b', name): return 'Reis, Nudeln & Getreide'
    if re.search(r'\b(pao|wrap|bagel|bolacha|tortilha)\b', name): return 'Brot & Backwaren'
    return 'Sonstiges / Prüfen'


def purchase_state(name: str, state: str) -> str:
    return 'purchase_as_is' if name in PURCHASE_STABLE else state


def supermarket_rows(items: list[dict], *, yields: dict[str,dict]|None=None) -> list[dict]:
    """Consolidate retail quantities; only reviewed yields convert to raw buying mass.

    A reviewed yield is specific to the product, preparation state and method.
    A cooked-only product still needs a yield to become a raw shopping amount.
    Do not add unconverted cooked weights to raw weights.
    """
    yields=yields or {}
    grouped: dict[tuple[str,str],list[dict]] = defaultdict(list)
    for item in items:
        grouped[(item['ingredient'],item['unit'])].append(item)
    results=[]
    for (name,unit),entries in grouped.items():
        breakdown={}
        for ent in entries:
            s=ent['state']
            breakdown[s]=breakdown.get(s,0.0)+float(ent['quantity'])
        recipes=sorted({r.strip() for ent in entries for r in ent.get('recipes','').split(',') if r.strip()})
        quantity=0.0
        pending=[]
        conversions=[]
        for state,value in breakdown.items():
            if name in PURCHASE_STABLE or state in {'raw','unknown','as_served'} and not (
                state=='as_served' and 'raw' in breakdown and name not in PURCHASE_STABLE
            ):
                # 'as_served' alone stays as served; if mixed with raw, a purchase
                # meaning is required before summing those masses.
                quantity+=value
                continue
            if unit=='g' and (state in {'cooked','drained','as_served'}):
                reviewed=yields.get(f'{name}|{state}')
                if reviewed:
                    quantity+=value/float(reviewed['factor'])
                    conversions.append(f'{value:g} g ({state}) → {value/float(reviewed["factor"]):.1f} g raw '
                                       f'[yield {reviewed["factor"]:.3g}; {reviewed["method"]}; {reviewed["source"]}]')
                    continue
            pending.append(f'{value:g} {unit} ({state})')
        requires_conversion=bool(pending)
        if requires_conversion:
            # Keep all components visible when a single purchase total is unsafe.
            components=' + '.join(f'{v:g} {unit} ({st})' for st,v in sorted(breakdown.items()))
            note='Roh-/Gargewicht prüfen; Umrechnung nötig: '+', '.join(pending)
            if conversions: note+='; Bereits umgerechnet: '+'; '.join(conversions)
            quantity_display=components
            quantity_out=None
        else:
            if unit=='un':
                original=quantity
                quantity=ceil(quantity-1e-9)
                if quantity!=original:
                    conversions.append(f'Für Einkauf gerundet ({original:.2f} Stück geplant)')
            note='; '.join(conversions)
            quantity_display=f'{quantity:g} {unit}'
            quantity_out=quantity
        results.append({
            'section':section_for(name),'ingredient':name,'label':product_label(name),
            'quantity':quantity_out,'unit':unit,'quantity_display':quantity_display,
            'states':breakdown,'note':note,'recipes':', '.join(recipes),
            'requires_conversion':requires_conversion,
            'conversion_detail':conversions,'pending_states':pending,
        })
    order={section:i for i,section in enumerate(SECTIONS)}
    return sorted(results,key=lambda row:(order[row['section']],row['label'].casefold(),row['unit']))
