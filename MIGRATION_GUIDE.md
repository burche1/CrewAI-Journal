# CrewAI Journal: Machine Migration and Incremental Rewrite

## Scope and protection

This package contains **byte-for-byte copies** of the two uploaded source files. It does not contain credentials, OAuth tokens, personal notes, ebooks, database files or the previous machine's layout configuration. **Do not run `journal_v3.py` yet**; it has hardcoded paths and side-effecting tools. The migration doctor is safe to run offline.

## Phase 1 — Install the Python environment (Ubuntu)

Install distribution libraries required by PDF generation:

```bash
sudo apt update
sudo apt install -y curl git build-essential python3-dev libpango-1.0-0 \
  libharfbuzz0b libpangoft2-1.0-0 libharfbuzz-subset0 libffi-dev \
  libjpeg-dev libopenjp2-7-dev
```

Install `uv` following its official instructions (review the installer first if preferred):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Restart your shell, or update PATH if needed:
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.12
```

From the directory containing this kit:

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements-migration.txt
python doctor.py
python -m weasyprint --info
```

`requirements-migration.txt` is an initial list inferred from imports, not a frozen or tested dependency set. If resolution/import conflicts occur, save the output. After reaching a working baseline, freeze versions and add regression tests before upgrading anything.

## Phase 2 — Initialize local configuration without credentials

```bash
cp .env.example .env
cp config.example.json config.json
cp layout.example.css layout.css
mkdir -p Editions Books Training_db
python doctor.py
```

`.env`, `config.json`, `layout.css`, Books/, Editions/, and Training_db/ are local-only in the starter `.gitignore`. These placeholders are NOT equivalent to your original assets. Never copy company credentials or company data into the project without appropriate authorization.

## Phase 3 — Inventory and refactor

1. Inventory actual Obsidian vault directories and authorization boundaries. Remove absolute paths from `tools.py` and `journal_v3.py`.
2. Separate pure deterministic functions from CrewAI-decorated tools.
3. Repair calendar timezone/date arithmetic, chess FEN reconstruction and nutrition accounting.
4. Remove duplicate ebook and puzzle generation; make reads repeatable and side effects explicit.
5. Replace shared `/tmp/...` files with a per-run workspace and typed outputs.
6. Replace fragile news search with NewsCollector v0.8.0 JSON adapter; keep the databases distinct.
7. Validate structured CrewAI output and render the PDF independently of LLM execution.
8. Introduce unit tests, offline fixtures and integration tests before enabling live services.

## External services (enable individually)

- **OpenAI:** `.env` with local key, test a single minimal model request only after deciding to use it.
- **Obsidian:** choose a permitted vault or subfolder; do not automatically give agents access to all personal notes.
- **Google Workspace:** run read-only OAuth setup only on an appropriate account; protect `credentials.json` and `token.json`; never commit them.
- **NewsCollector:** connect through validated JSON commands or a Python adapter with fixed arguments; agents should never receive arbitrary shell access or database filenames.
- **Chess, weather, ebooks, games:** test these isolated tools with sample data before rebuilding the daily crew.

## Completion criteria

- Python 3.12 project-specific `.venv` works.
- `python doctor.py` reports all Python packages available and two parseable source files.
- `python -m weasyprint --info` works on Ubuntu.
- No sensitive data or real API calls are required to reach this baseline.
- Do NOT run `python journal_v3.py` until path/configuration and side effects are refactored.
