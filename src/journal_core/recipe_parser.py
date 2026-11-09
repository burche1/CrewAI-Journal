"""Read only the six explicitly configured source files; parse recipe sections.

Nutrition and shopping values are NOT inferred. Amounts are parsed conservatively.
"""
from __future__ import annotations
from collections import Counter
import hashlib
from pathlib import Path
import re
from .models import Ingredient, Recipe
from .paths import recipe_paths

HEADER_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
RECIPE_RE = re.compile(r"^(\d{2,})\.\s+(.+?)\s*$")
PORTION_RE = re.compile(r"^\s*\*\*(Você|Esposa):\*\*\s*(.+?)\s*$", re.M)
FIELD_RE = re.compile(r"\*\*(Modo de preparo|Organização(?: e conservação)?|Quando usar|Categoria|Tempo(?: no domingo| na hora| no jantar| no horário do almoço)?):\*\*\s*([^\n]*?)(?=\s+\*\*[^\n]+?:\*\*|$)", re.M)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+(?:\([^)]*\)[^\s)]*)*)\)", re.I)
QUANTITY_RE = re.compile(r"^\s*(\d+(?:[.,]\d+)?|½|¼|¾)\s*(kg|g|ml|l|unidades?|unid\.?|colheres?|xícaras?)?\b\s*(.*)$", re.I)


def _ingredient_state(category: str, name: str) -> str:
    n = name.casefold()
    if re.search(r"\b(cozid[oa]s?|pront[oa]s?)\b", n):
        return "cooked"
    if re.search(r"\b(escorrid[oa]s?)\b", n):
        return "drained"
    if re.search(r"\b(cru[as]?|sec[oa]s?)\b", n):
        return "raw"
    # Deliberately avoid guessing from category-level descriptions.
    return "unknown"


def split_portion_ingredients(portion: str) -> list[str]:
    """Split only top-level comma separators, preserving commas in descriptions.

    E.g. '400 g chili pronto (com carne, feijão e tomate), 260 g arroz cozido'
    contains TWO ingredients rather than three.
    """
    parts, part, depth = [], [], 0
    for i, char in enumerate(portion):
        if char in '([':
            depth += 1
        elif char in ')]':
            depth = max(0,depth-1)
        if char == ',' and depth == 0 and i+1 < len(portion) and portion[i+1].isspace():
            parts.append(''.join(part).strip())
            part=[]
        else:
            part.append(char)
    if part:
        parts.append(''.join(part).strip())
    return parts


def parse_ingredients(portion: str, category: str) -> list[Ingredient]:
    items: list[Ingredient] = []
    for raw in split_portion_ingredients(portion):
        raw = raw.strip().rstrip(".")
        if not raw:
            continue
        optional = bool(re.search(r"\bopcional\b", raw, re.I))
        ambiguous = bool(re.search(r"\s/\s|[\wÀ-ÿ]/[\wÀ-ÿ]|\b(?:ou|a gosto|uma fruta|1 fruta|fruta da estação)\b", raw, re.I))
        m = QUANTITY_RE.match(raw)
        qty = None
        unit = None
        name = raw
        issues: list[str] = []
        if m:
            numeric = {"½": 0.5, "¼": 0.25, "¾": 0.75}
            qty = numeric.get(m.group(1), None)
            if qty is None:
                qty = float(m.group(1).replace(",", "."))
            unit = (m.group(2) or "item").lower()
            name = m.group(3).strip() or raw
        else:
            issues.append("No explicit leading quantity; cannot calculate amount")
        if ambiguous:
            issues.append("Alternative/composite ingredient needs user choice")
        if optional:
            issues.append("Optional ingredient; decide inclusion before shopping")
        state = _ingredient_state(category, name)
        if state == "unknown":
            issues.append("Raw/cooked/served state not verified")
        items.append(Ingredient(raw=raw, name=name, quantity=qty, unit=unit,
                                measurement_state=state, optional=optional,
                                ambiguous=ambiguous, issues=issues))
    return items


def parse_recipe_file(path: Path, category: str) -> list[Recipe]:
    if category not in {"breakfast", "lunch", "dinner", "snacks"}:
        raise ValueError(f"Unknown category: {category}")
    content = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    headers = list(HEADER_RE.finditer(content))
    recipes: list[Recipe] = []
    for index, heading in enumerate(headers):
        if heading.group(1) != "###":
            continue
        match = RECIPE_RE.match(heading.group(2))
        if not match:
            continue
        number, title = int(match.group(1)), match.group(2)
        next_offset = headers[index + 1].start() if index + 1 < len(headers) else len(content)
        segment = content[heading.end():next_offset].strip()
        segment = re.sub(r"(?:\n\s*---\s*)+$", "", segment).strip()
        portions_found = PORTION_RE.findall(segment)
        if len(portions_found) != 2 or {key for key, _ in portions_found} != {"Você", "Esposa"}:
            raise ValueError(f"{category}:{number:02d} needs one Você and one Esposa portion")
        portions = {("person_a" if key == "Você" else "person_b"): val.strip() for key, val in portions_found}
        details = {}
        for field, value in FIELD_RE.findall(segment):
            details[field] = value.strip()
        start_line = content.count("\n", 0, heading.start()) + 1
        end_line = max(start_line, content.count("\n", 0, next_offset))
        recipe = Recipe(
            id=f"{category}:{number:02d}", category=category, number=number,
            title=title, source_file=str(path), source_sha256=digest,
            source_start_line=start_line, source_end_line=end_line,
            portions=portions,
            ingredients={p: parse_ingredients(v, category) for p, v in portions.items()},
            image_url=(IMAGE_RE.search(segment).group(1) if IMAGE_RE.search(segment) else None),
            preparation=details.get("Modo de preparo"),
            organization=details.get("Organização") or details.get("Organização e conservação"),
            details=details, markdown=f"### {number:02d}. {title}\n\n{segment}",
        )
        if not recipe.preparation:
            recipe.warnings.append("Preparation description could not be extracted")
        recipes.append(recipe)
    ids = [r.id for r in recipes]
    if len(set(ids)) != len(ids):
        dup = [x for x, count in Counter(ids).items() if count > 1]
        raise ValueError(f"Duplicate recipe IDs in {path}: {dup}")
    return sorted(recipes, key=lambda r: r.number)


def load_catalog() -> dict[str, list[Recipe]]:
    return {cat: parse_recipe_file(path, cat) for cat, path in recipe_paths().items()}


def get_recipe(catalog: dict[str, list[Recipe]], recipe_id: str) -> Recipe:
    for recipes in catalog.values():
        for recipe in recipes:
            if recipe.id == recipe_id:
                return recipe
    raise KeyError(f"Recipe ID not found: {recipe_id}")
