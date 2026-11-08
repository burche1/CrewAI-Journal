"""Safe, read-only migration preflight for CrewAI Journal.

Does not import the project (which may create agents), run tools, call APIs,
read secret values, modify state, or produce PDFs.
"""
import ast
import importlib.util
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = {
    "crewai": "crewai",
    "pydantic": "pydantic",
    "dotenv": "python-dotenv",
    "markdown": "markdown",
    "weasyprint": "weasyprint",
    "requests": "requests",
    "sudoku": "py-sudoku",
    "pandas": "pandas",
    "PyPDF2": "PyPDF2",
    "ebooklib": "EbookLib",
    "bs4": "beautifulsoup4",
    "google.auth": "google-auth",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "googleapiclient": "google-api-python-client",
    "chess": "chess",
    "duckduckgo_search": "duckduckgo-search (legacy import)",
}

def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False

def run() -> int:
    print("CrewAI Journal — migration preflight (no network calls)")
    print(f"Python: {sys.version.split()[0]} | OS: {platform.platform()}")
    print(f"Virtual env: {'yes' if sys.prefix != sys.base_prefix else 'NO'}")
    if not ((3, 10) <= sys.version_info[:2] < (3, 14)):
        print("WARNING: Python outside CrewAI-supported 3.10–3.13 range")
    print("\nSource files:")
    for name in ("journal_v3.py", "tools.py"):
        file = ROOT / name
        try:
            ast.parse(file.read_text(encoding="utf-8"), filename=name)
            print(f"  OK: {name} parses")
        except (OSError, SyntaxError) as exc:
            print(f"  ERROR: {name}: {exc}")
    print("\nPython packages:")
    missing = []
    for mod, package in MODULES.items():
        if module_available(mod):
            print(f"  OK: {package}")
        else:
            missing.append(package)
            print(f"  MISSING: {package}")
    print("\nLocal configuration (presence only; secrets never read):")
    for name in (".env", "config.json", "layout.css", "credentials.json", "token.json"):
        print(f"  {name}: {'present' if (ROOT / name).is_file() else 'not present'}")
    if (ROOT / "config.json").is_file():
        try:
            cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            reading = cfg.get("leitura", {})
            expected = {"fonte", "livro_local_nome", "livro_internet_url"}
            print("  config.json reading keys: " + ("OK" if expected.issubset(reading) else "MISSING KEYS"))
        except (ValueError, OSError) as exc:
            print(f"  config.json: invalid ({type(exc).__name__})")
    print("\nNote: a clean preflight is NOT proof the full journal runs.")
    print("Legacy absolute paths, OAuth setup, network tools and PDF layout require migration.")
    return 0 if not missing else 1

if __name__ == "__main__":
    raise SystemExit(run())
