"""Read local paths from existing settings.py/.env; don't access secrets."""
from __future__ import annotations
from pathlib import Path
import settings

RECIPE_KEYS = {
    "breakfast": "BREAKFAST_INVENTORY_FILE",
    "lunch": "LUNCH_INVENTORY_FILE",
    "dinner": "DINNER_INVENTORY_FILE",
    "snacks": "SNACK_INVENTORY_FILE",
}


def recipe_paths() -> dict[str, Path]:
    output = {}
    for category, key in RECIPE_KEYS.items():
        path = settings.configured_path(key)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"{key} is unset or not a file. Set it in .env: {path}")
        output[category] = path
    return output


def training_paths() -> tuple[Path, Path]:
    endurance = settings.configured_path("TRAINING_PLAN_FILE")
    gym = settings.configured_path("GYM_PLAN_FILE")
    for name, path in (("TRAINING_PLAN_FILE", endurance), ("GYM_PLAN_FILE", gym)):
        if path is None or not path.is_file():
            raise FileNotFoundError(f"{name} is unset or not a file. Set it in .env: {path}")
    return endurance, gym


def database_path() -> Path:
    return settings.JOURNAL_STATE_DIR / "journal_core.sqlite3"
