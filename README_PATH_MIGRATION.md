# CrewAI Journal — Path Migration (Stage 1)

This package updates the two source files you provided, keeping the current application structure. It does **not** run agents, authorize Google, migrate or copy your personal files, or replace your current `.env` or `config.json`.

## 1. Back up the current sources

```bash
cd ~/Documents/CrewAI-Journal/CrewAI_Journal
cp -a journal_v3.py journal_v3.py.before-path-migration
cp -a tools.py tools.py.before-path-migration
```

Keep your `.env` and `credentials.json` private. Do not upload or commit them.

## 2. Extract the patch

Download the ZIP into ~/Downloads and run:

```bash
unzip -o ~/Downloads/CrewAI_Journal_path_migration.zip -d .
```

The ZIP contains only: `journal_v3.py`, `tools.py`, `settings.py`, `.env.paths.example`, `check_paths.py`, and this guide. There is **no** `.env`, `config.json`, `credentials.json`, `token.json`, `data/`, or `.venv/` in the package.

## 3. Configure paths

Open your existing `.env` and append values from `.env.paths.example` (do not replace its contents). Keep the existing API keys. Make sure the two Obsidian folders exist. Do not set JOURNAL_NOTES_PATH to an entire vault without explicitly deciding that access is acceptable. Locate the specific journal and training documents first.

Before enabling the training tool, set `TRAINING_PLAN_FILE` to the exact Markdown file you want to use. Leaving it unset produces a controlled error instead of accessing the previous computer path. `BOOKS_DIR` defaults to `Books/` inside this project. Google tokens are now placed in `data/state/google_token.json`, while client credentials default to the existing `credentials.json` in the project root.

If you have old reading/training tracker JSON files, copy them to `data/state/` explicitly **after** verifying they correspond to this journal. The patch never advances them by itself.

## 4. Validate without running any agents

```bash
source .venv/bin/activate
python check_paths.py
python -m py_compile settings.py journal_v3.py tools.py check_paths.py
python doctor.py
```

You can grep for stale machine-specific paths:

```bash
grep -nE '/home/alexandre\.|/tmp/|layout\.css|token\.json' journal_v3.py tools.py settings.py
```

`layout.css` and `token.json` may appear as portable **relative file names**, but there should be no obsolete absolute paths. `check_paths.py` reports missing optional resources; it does not create them.

## Still outstanding (do not execute the whole journal yet)

- Obsidian read tools accept arbitrary agent-provided directory arguments; restrict them to an explicit allowlist before running the crew.
- The training tracker can still advance when the training tool is called; reading tools can advance reading trackers. Make them idempotent before full runs.
- Google OAuth must be reauthorized deliberately; Calendar date handling needs correction.
- `layout.css` is absent in the new machine. The patched renderer prints a warning and can generate an unstyled PDF if other dependencies are satisfied; recover/recreate the layout later.
- The old PDF/LLM flow and news, chess and nutrition logic are unchanged; this is a **path migration**, not a claim that the application now runs end-to-end.
- Legacy `data/runtime` filenames are still fixed. Run-scoped temp paths will be part of the next refactor.
- Tool permissions, symlinks, remote URLs, and corporate-data handling need a separate security review.
