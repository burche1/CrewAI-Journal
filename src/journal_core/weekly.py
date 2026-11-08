"""First weekly menu workflow: manual picks, immutable approved menu.

No AI reordering, personalized macro/portion adjustments or shopping totals yet.
"""
from __future__ import annotations
from datetime import date, timedelta
from .models import Recipe, WeeklyMenu
from .recipe_parser import get_recipe

CATEGORIES = ("breakfast", "lunch", "dinner", "snacks")


def monday_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def create_menu(week_start: date, catalog: dict[str, list[Recipe]], selections: dict[str, list[str]]) -> WeeklyMenu:
    if week_start.weekday() != 0:
        raise ValueError("Start date must be a Monday (YYYY-MM-DD)")
    hashes = {}
    for cat in CATEGORIES:
        ids = selections.get(cat)
        if ids is None or len(ids) != 7 or len(set(ids)) != 7:
            raise ValueError(f"Choose exactly seven distinct {cat} recipes")
        for rid in ids:
            if not rid.startswith(cat + ":"):
                raise ValueError(f"Recipe {rid} is not part of category {cat}")
            recipe = get_recipe(catalog, rid)
            hashes[cat] = recipe.source_sha256
    return WeeklyMenu(week_start=week_start.isoformat(), selections=selections, source_hashes=hashes)


def day_menu(on_date: date, menu: WeeklyMenu, catalog: dict[str, list[Recipe]]) -> dict:
    start = date.fromisoformat(menu.week_start)
    index = (on_date - start).days
    if not 0 <= index <= 6:
        raise ValueError("Date is outside the weekly plan")
    result = {"date": on_date.isoformat(), "plan_week": menu.week_start, "status": menu.status,
              "portion_factors": menu.portion_factors, "meals": {}, "source_changed": []}
    for category, ids in menu.selections.items():
        r = get_recipe(catalog, ids[index])
        result["meals"][category] = {
            "id": r.id, "title": r.title, "portions": r.portions,
            "scaled_ingredients": {
                person: [dict(raw=x.raw, name=x.name, quantity=round(x.quantity * menu.portion_factors.get(person, 1.0), 2) if x.quantity is not None else None,
                              unit=x.unit, ambiguous=x.ambiguous, optional=x.optional)
                         for x in r.ingredients[person]]
                for person in ('person_a', 'person_b')
            },
            "preparation": r.preparation, "organization": r.organization,
            "source": f"{r.source_file}:{r.source_start_line}",
        }
        if r.source_sha256 != menu.source_hashes.get(category):
            result["source_changed"].append(category)
    return result
