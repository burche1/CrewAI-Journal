"""Offline, read-only path diagnosis for the CrewAI Journal migration.

Does not import tools.py or run CrewAI, authenticate, fetch data, or modify state.
"""
from pathlib import Path
from settings import (
    PROJECT_ROOT, OBSIDIAN_VAULT_PATH, LEGACY_OBSIDIAN_PATH,
    JOURNAL_NOTES_PATH, TRAINING_PLAN_FILE, JOURNAL_STATE_DIR,
    JOURNAL_RUNTIME_DIR, JOURNAL_OUTPUT_DIR, BOOKS_DIR,
    JOURNAL_CONFIG_FILE, JOURNAL_STYLE_FILE,
    GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE, NEWSCOLLECTOR_PATH,
)

def check(name: str, path: Path | None, kind: str = "either") -> None:
    if path is None:
        print(f"SET ME  {name}: not configured")
        return
    available = (path.is_dir() if kind == "dir" else path.is_file() if kind == "file" else path.exists())
    status = "OK" if available else "MISSING (or not created yet)"
    print(f"{status:<28} {name}: {path}")

if __name__ == "__main__":
    print("CrewAI Journal — paths only (no network or agent execution)")
    print(f"Project: {PROJECT_ROOT}")
    check("Current Obsidian vault", OBSIDIAN_VAULT_PATH, "dir")
    check("Syncthing mirror", LEGACY_OBSIDIAN_PATH, "dir")
    check("Authorized journal notes", JOURNAL_NOTES_PATH, "dir")
    check("Training file", TRAINING_PLAN_FILE, "file")
    check("Books folder", BOOKS_DIR, "dir")
    check("State directory", JOURNAL_STATE_DIR, "dir")
    check("Runtime directory", JOURNAL_RUNTIME_DIR, "dir")
    check("Output directory", JOURNAL_OUTPUT_DIR, "dir")
    check("config.json", JOURNAL_CONFIG_FILE, "file")
    check("PDF stylesheet", JOURNAL_STYLE_FILE, "file")
    check("Google client configuration", GOOGLE_CREDENTIALS_FILE, "file")
    check("Google token", GOOGLE_TOKEN_FILE, "file")
    check("NewsCollector", NEWSCOLLECTOR_PATH, "dir")
    print("Missing optional paths are not errors until that integration is enabled.")
