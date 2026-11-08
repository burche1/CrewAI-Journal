"""Centralized, portable paths for CrewAI Journal (path migration stage).

Read .env from the project root, irrespective of the current working directory.
No network or agent actions occur at import time.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def configured_path(name: str, default: str | Path | None = None) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw and default is None:
        return None
    path = Path(raw).expanduser() if raw else Path(default).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve(strict=False)


OBSIDIAN_VAULT_PATH = configured_path(
    "OBSIDIAN_VAULT_PATH", Path.home() / "Documents" / "Personal-AI-Workspace"
)
LEGACY_OBSIDIAN_PATH = configured_path(
    "LEGACY_OBSIDIAN_PATH", Path.home() / "Documents" / "Obsidian-OldPC-Mirror"
)
# Deliberately no fallback for the notes used by agents or the training plan.
# Do not expose an entire Obsidian vault to an agent as a default.
JOURNAL_NOTES_PATH = configured_path("JOURNAL_NOTES_PATH")
TRAINING_PLAN_FILE = configured_path("TRAINING_PLAN_FILE")

# Training and strength plans
GYM_PLAN_FILE = configured_path("GYM_PLAN_FILE")

# Curated meal inventories
MEAL_INVENTORY_FILES = {
    "breakfast": configured_path("BREAKFAST_INVENTORY_FILE"),
    "lunch": configured_path("LUNCH_INVENTORY_FILE"),
    "dinner": configured_path("DINNER_INVENTORY_FILE"),
    "snacks": configured_path("SNACK_INVENTORY_FILE"),
}

JOURNAL_DATA_DIR = configured_path("JOURNAL_DATA_DIR", "data")
JOURNAL_STATE_DIR = configured_path("JOURNAL_STATE_DIR", JOURNAL_DATA_DIR / "state")
JOURNAL_RUNTIME_DIR = configured_path("JOURNAL_RUNTIME_DIR", JOURNAL_DATA_DIR / "runtime")
JOURNAL_OUTPUT_DIR = configured_path("JOURNAL_OUTPUT_DIR", "outputs/pdf")
BOOKS_DIR = configured_path("BOOKS_DIR", "Books")

JOURNAL_CONFIG_FILE = configured_path("JOURNAL_CONFIG_FILE", "config.json")
JOURNAL_STYLE_FILE = configured_path("JOURNAL_STYLE_FILE", "layout.css")
GOOGLE_CREDENTIALS_FILE = configured_path("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE = configured_path(
    "GOOGLE_TOKEN_FILE", JOURNAL_STATE_DIR / "google_token.json"
)
NEWSCOLLECTOR_PATH = configured_path("NEWSCOLLECTOR_PATH")


def runtime_file(filename: str) -> Path:
    """Shared legacy runtime directory; isolate each run in a later refactor."""
    JOURNAL_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    return JOURNAL_RUNTIME_DIR / filename
