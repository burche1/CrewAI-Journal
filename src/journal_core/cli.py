"""Standalone offline CLI. See README for command examples."""
from __future__ import annotations
import argparse
from datetime import date
import json
import re
import sys
from .models import WeeklyMenu
from .paths import recipe_paths, training_paths, database_path
from .recipe_parser import load_catalog, get_recipe
from .state import set_week, get_week, save_menu, load_menu, approve_menu
from .training_parser import load_training
from .weekly import CATEGORIES, create_menu, day_menu, monday_start
from .schedule import (anchor_training, week_for_date, pause_training, resume_training, get_schedule)
from .shopping import shopping_list, as_csv, as_markdown
from .reviews import load_reviews
from .reviews import load_reviews
from .nutrition import week_nutrition
from pathlib import Path


def output(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Date must be YYYY-MM-DD") from exc


def validate_week(week: str) -> str:
    week = str(week).strip().upper()
    if re.fullmatch(r"P[1-4]", week):
        return week
    if week.startswith("W"):
        week = week[1:]
    if not week.isdigit() or not 1 <= int(week) <= 52:
        raise ValueError("Week must be P1–P4 or W1–W52")
    return str(int(week))


def interactive_choices(category, recipes):
    print(f"\n{category.upper()} — choose SEVEN distinct recipe numbers in desired weekday order")
    for r in recipes:
        print(f" {r.number:02d}  {r.title}")
    while True:
        entered = input(f"{category} (example: 01,03,05,07,09,11,13; q to stop): ").strip()
        if entered.lower() == "q":
            raise KeyboardInterrupt()
        pieces = re.split(r"[;,\s]+", entered)
        if len(pieces) != 7:
            print("Please choose exactly seven numbers.")
            continue
        try:
            numbers = [int(s) for s in pieces]
        except ValueError:
            print("Use recipe numbers separated by commas.")
            continue
        available = {r.number for r in recipes}
        if len(set(numbers)) != 7 or any(n not in available for n in numbers):
            print("Numbers must be distinct and available in this category.")
            continue
        return [f"{category}:{number:02d}" for number in numbers]


def main(argv=None):
    parser = argparse.ArgumentParser(prog="journal_core.py", description="Offline deterministic journal core")
    commands = parser.add_subparsers(dest="cmd", required=True)
    commands.add_parser("check", help="Validate configured recipe and training sources")
    catalog_p = commands.add_parser("catalog")
    catalog_sub = catalog_p.add_subparsers(dest="action", required=True)
    catalog_sub.add_parser("summary")
    catalog_list = catalog_sub.add_parser("list")
    catalog_list.add_argument("--category", choices=CATEGORIES, required=True)
    catalog_show = catalog_sub.add_parser("show")
    catalog_show.add_argument("recipe_id", help="e.g. breakfast:01")
    training_p = commands.add_parser("training")
    training_sub = training_p.add_subparsers(dest="action", required=True)
    training_status = training_sub.add_parser("status")
    training_status.add_argument("--date", default=date.today().isoformat())
    training_schedule = training_sub.add_parser("schedule", help="Start calendar progression P1-P4, W1-W52")
    training_schedule.add_argument("--start", required=True, help="Monday YYYY-MM-DD")
    training_schedule.add_argument("--week", default="P1")
    training_pause = training_sub.add_parser("pause")
    training_pause.add_argument("--date", default=date.today().isoformat())
    training_resume = training_sub.add_parser("resume")
    training_resume.add_argument("--start", required=True, help="Resume on Monday")
    training_resume.add_argument("--week", help="Optional different week on resumption")
    training_set = training_sub.add_parser("set-week")
    training_set.add_argument("week", help="P1, P2, P3, P4, W1...W52")
    training_set.add_argument("--note", default="", help="Reason for manually setting phase")
    training_preview = training_sub.add_parser("preview")
    training_preview.add_argument("--date", required=True)
    training_preview.add_argument("--week", help="Optional override; does not change saved state")
    week_p = commands.add_parser("week")
    week_sub = week_p.add_subparsers(dest="action", required=True)
    plan_p = week_sub.add_parser("plan")
    plan_p.add_argument("--start", required=True, help="Monday YYYY-MM-DD")
    approve_p = week_sub.add_parser("approve")
    approve_p.add_argument("--start", required=True)
    show_p = week_sub.add_parser("show")
    show_p.add_argument("--date", required=True)
    shopping_p = week_sub.add_parser("shopping", help="Audit and export a weekly shopping list")
    shopping_p.add_argument("--start", required=True)
    shopping_p.add_argument("--format", choices=['json','md','csv'], default='md')
    shopping_p.add_argument("--out", help="Optional output file path; never overwrites")
    nutrition_p = week_sub.add_parser("nutrition", help="Partial nutrition subtotals")
    nutrition_p.add_argument("--start", required=True)
    day_p = commands.add_parser("day")
    day_p.add_argument("--date", required=True)
    day_p.add_argument("--week", help="Optional override for training; no state write")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "check":
            catalog = load_catalog()
            training = load_training()
            info = {category: len(recipes) for category, recipes in catalog.items()}
            count = sum(info.values())
            if info != {cat: 30 for cat in CATEGORIES} or any(
                {r.number for r in recipes} != set(range(1, 31))
                for recipes in catalog.values()
            ):
                raise ValueError(f"Expected recipe numbers 01–30 per file; found {info}")
            output({"status": "ok", "recipe_counts": info, "total_recipes": count,
                    "preparation_weeks": sorted(training.prep),
                    "main_cycle_week_count": len(training.main), "race_week": 51, "recovery_week": 52,
                    "database_path": str(database_path()),
                    "state_database_exists": database_path().is_file(),
                    "note": "Source parse only; no macros, shopping, LLM or journal PDF"})
        elif args.cmd == "catalog":
            catalog = load_catalog()
            if args.action == "summary":
                output({k: {"count": len(v), "first": v[0].id, "last": v[-1].id,
                            "missing_preparation": [r.id for r in v if not r.preparation]} for k, v in catalog.items()})
            elif args.action == "list":
                for r in catalog[args.category]:
                    print(f"{r.id}  {r.title}")
            else:
                output(get_recipe(catalog, args.recipe_id))
        elif args.cmd == "training":
            if args.action == 'schedule':
                output(anchor_training(parse_date(args.start), validate_week(args.week)))
            elif args.action == 'pause':
                output(pause_training(parse_date(args.date)))
            elif args.action == 'resume':
                output(resume_training(parse_date(args.start), week=args.week))
            elif args.action == 'status':
                target = parse_date(args.date)
                schedule = get_schedule()
                if schedule:
                    try:
                        output({'date':target.isoformat(), 'schedule':schedule,
                                'resolved': week_for_date(target)})
                    except ValueError as exc:
                        output({'date':target.isoformat(), 'schedule':schedule,'note':str(exc)})
                else:
                    manual = get_week()
                    output({'date':target.isoformat(), 'mode':'legacy_manual',
                            'training_week': manual[0] if manual else None,
                            'note':'Run training schedule --start YYYY-MM-DD to activate automatic progression.'})
            elif args.action == 'set-week':
                code = validate_week(args.week)
                # Keep prior invocation useful: re-anchor from the current Monday.
                anchor = monday_start(date.today())
                set_week(code,note=args.note)  # legacy audit for old installations
                output(anchor_training(anchor, code, note=args.note or 'Re-anchored through set-week'))
            else:
                target = parse_date(args.date)
                info = None if args.week else week_for_date(target)
                manual = get_week() if info is None and not args.week else None
                selected = args.week or (info['week'] if info else (manual[0] if manual else None))
                if not selected:
                    raise ValueError("No training schedule set. Use training schedule --start YYYY-MM-DD")
                preview=load_training().preview(target, validate_week(selected)).model_dump(mode='json')
                preview['training_schedule'] = info or {'source':'explicit_override' if args.week else 'legacy_manual'}
                output(preview)
        elif args.cmd == "week":
            if args.action == "plan":
                start = parse_date(args.start)
                catalog = load_catalog()
                selections = {category: interactive_choices(category, catalog[category]) for category in CATEGORIES}
                menu = create_menu(start, catalog, selections)
                print("\nDRAFT weekly menu (one selected recipe per category and day):")
                for offset in range(7):
                    from datetime import timedelta
                    d = start + timedelta(days=offset)
                    daily = day_menu(d, menu, catalog)
                    print(d.isoformat(), " | ".join(f"{key}: {v['title']}" for key,v in daily['meals'].items()))
                yes = input("Save this DRAFT? [y/N]: ").strip().lower()
                if yes != "y":
                    print("Not saved")
                    return 0
                save_menu(menu)
                output({"saved": True, "week_start": menu.week_start, "status": "draft",
                        "next": f"python journal_core.py week approve --start {menu.week_start}"})
            elif args.action == "approve":
                start = parse_date(args.start)
                if start.weekday() != 0:
                    raise ValueError("Week start must be Monday")
                menu = load_menu(start.isoformat())
                if menu is None:
                    raise ValueError("No draft found for this week")
                catalog = load_catalog()
                changes = [category for category, recipes in catalog.items()
                           if recipes[0].source_sha256 != menu.source_hashes.get(category)]
                if changes:
                    raise ValueError(f"Recipe source changed after selection: {changes}. Review and recreate draft")
                approve_menu(start.isoformat())
                output({"week_start": start.isoformat(), "status": "approved"})
            elif args.action in ('shopping','nutrition'):
                start = parse_date(args.start)
                if start.weekday()!=0:
                    raise ValueError('Week start must be Monday')
                menu = load_menu(start.isoformat())
                if not menu or menu.status != 'approved':
                    raise ValueError('An APPROVED weekly menu is required')
                catalog = load_catalog()
                changed = [cat for cat,rows in catalog.items()
                           if rows[0].source_sha256 != menu.source_hashes.get(cat)]
                if changed:
                    raise ValueError(f'Source Markdown changed since approval: {changed}')
                if args.action == 'shopping':
                    result = shopping_list(menu,catalog,resolutions=load_reviews(menu.week_start))
                    body = {'json': lambda:json.dumps(result,ensure_ascii=False,indent=2),
                            'md':lambda:as_markdown(result), 'csv':lambda:as_csv(result)}[args.format]()
                    if args.out:
                        path=Path(args.out).expanduser()
                        path.parent.mkdir(parents=True,exist_ok=True)
                        with path.open('x',encoding='utf-8') as file:
                            file.write(body)
                        output({'saved':str(path),'unresolved_items':len(result['needs_review'])})
                    else:
                        print(body)
                else:
                    output(week_nutrition(menu,catalog))
            else:
                d = parse_date(args.date)
                menu = load_menu(monday_start(d).isoformat())
                if not menu:
                    raise ValueError("No weekly menu found. Run 'week plan --start YYYY-MM-DD'")
                output(day_menu(d, menu, load_catalog()))
        elif args.cmd == "day":
            d = parse_date(args.date)
            menu = load_menu(monday_start(d).isoformat())
            if not menu or menu.status != "approved":
                raise ValueError("No APPROVED weekly menu for this date")
            info = None if args.week else week_for_date(d)
            state = get_week() if info is None and not args.week else None
            selected = args.week or (info['week'] if info else (state[0] if state else None))
            if not selected:
                raise ValueError("No training schedule set. Use 'training schedule --start YYYY-MM-DD'")
            meals = day_menu(d, menu, load_catalog())
            if meals["source_changed"]:
                raise ValueError(f"Recipe source changed since approval: {meals['source_changed']}")
            output({"date": d.isoformat(), "training": load_training().preview(d, validate_week(selected)).model_dump(mode="json"),
                    "training_schedule": info,
                    "meals": meals, "status": "preview_only", "writes": "none"})
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled, nothing saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
