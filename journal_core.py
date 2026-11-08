"""Offline CLI entrypoint. Does not modify legacy journal_v3.py/tools.py."""
from src.journal_core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
