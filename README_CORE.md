# CrewAI Journal — Core v0.2 upgrade

This **incremental upgrade** replaces selected `src/journal_core/` Python modules from v0.1 and adds a **local web planner**, automatic calendar-based training progression, conservative nutrition subtotals and a reviewable shopping-list exporter. It does not run or alter your legacy `journal_v3.py` or `tools.py`, `.env`, Obsidian notes, Google setup or NewsCollector.

## What works now

1. **Automatic training progression:** set the Monday start once. P1 → P2 → P3 → P4 → W1 → ... → W52 advances by calendar week, whether or not you generate the journal. Read-only previews do not advance state. The schedule can be paused and resumed (or re-anchored) manually. After W52, the system indicates that the cycle has ended rather than looping silently.
2. **Clickable recipe picker:** locally hosted Streamlit interface with four searchable multiselect tabs, at most seven recipes per category, Monday–Sunday assignment table, source recipe previews, draft save and approval. Approved menus remain locked by design. All recipes remain sourced from six Markdown files indicated in `.env`.
3. **Portion adjustment:** editable **manual** factors for Person A and Person B (0.5–1.5). Scaled ingredient quantities appear in the daily JSON. These factors do not yet come from computed calorie/macro goals or exercise energy expenditure; they are preliminary.
4. **Shopping list:** aggregates compatible ingredient amounts across 28 chosen recipes, both people, with separate raw/cooked/drained/served groups. Includes the breakfast catalog's 50 ml/person/day coffee milk rule. Produces shopping Markdown and CSV; ambiguous and optional ingredients, fractional item counts and homemade prepared food are placed into a review list. **Resolve all review items and raw/cooked conversions before using it as a final grocery list.**
5. **Nutrition estimates:** starter food reference CSV with approximate demo per-100g/per-100ml values; computes **known subtotals** for kcal/protein/carbohydrates/fat and reports missing matches for every meal. Subtotals are not exact daily intake or complete macros, and are **not used to optimize quantities**. Users can replace the CSV with reviewed FoodData Central/package-label data, honoring raw/cooked basis and compatible units.
6. Existing v0.1 commands and DB tables continue working. SQLite schema migrates additively the first time a v0.2 writer runs. No code changes to your original CrewAI journal.

## Installation on your new ThinkPad

Open your CrewAI project and activate the environment:

```bash
cd ~/Documents/CrewAI-Journal/CrewAI_Journal
source .venv/bin/activate
```

**Back up your code and state first** (close Streamlit if it's running):

```bash
BACKUP_DIR="$HOME/Documents/CrewAI-Journal/core-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -a src/journal_core journal_core.py "$BACKUP_DIR/"
if [ -f data/state/journal_core.sqlite3 ]; then cp -a data/state/journal_core.sqlite3 "$BACKUP_DIR/"; fi
```

Download **`CrewAI_Journal_core_v0_2_update.zip`** to your Ubuntu `~/Downloads`, inspect, then extract the overlay:

```bash
unzip -l ~/Downloads/CrewAI_Journal_core_v0_2_update.zip
unzip -o ~/Downloads/CrewAI_Journal_core_v0_2_update.zip -d .
uv pip install -r requirements-planner.txt
```

> The ZIP contains only core Python modules, new UI/config/docs/tests; no `.env`, `settings.py`, Google secrets, source Markdown or state database. It overwrites the listed **core v0.1 modules**, but not `journal_v3.py` or `tools.py`. A separate backup above makes rollback straightforward.

Check all 120 recipe sources and 56 training weeks, then run the test suite:

```bash
python journal_core.py check
python -m unittest discover -s tests -v
```

## Automatic training timeline

For a **proposed** P1 start on Monday 2026-11-09, use:

```bash
python journal_core.py training schedule --start 2026-11-09 --week P1
python journal_core.py training status --date 2026-11-17  # P2
python journal_core.py training status --date 2026-12-07  # W1
python journal_core.py training preview --date 2026-11-17
```

The start date above is **only an example**. Choose the actual Monday when you begin P1, rather than recording workouts retroactively. If the plan proves too difficult, do not automatically raise exertion merely because the calendar advanced; use the safety overrides:

```bash
python journal_core.py training pause --date 2026-11-24
python journal_core.py training status --date 2026-12-01
python journal_core.py training resume --start 2026-12-07
# To change week intentionally, re-anchor:
python journal_core.py training schedule --start 2026-12-07 --week P2
```

Pause/resume/anchor operations create audit events. **No workouts are recorded as completed simply because the date changes.** A separate actual-activity log is a later feature.

**Legacy change:** `training set-week P1` now automatically re-anchors at *this week's Monday*, rather than simply storing a static week. Use `training schedule --start ...` for explicit historical dates.

## Launch the local weekly planner

```bash
streamlit run planner_app.py
```

Open **http://127.0.0.1:8501** on the same machine. `.streamlit/config.toml` binds to `127.0.0.1`, enables the default web protections, and disables usage-statistics telemetry. Close the server with **Ctrl+C** when finished.

1. Choose the desired week (Monday).
2. Click the four tabs and select seven recipes in each (searchable by name).
3. Use the editable weekday grid to rearrange those 28 choices. Every recipe must occur once per category.
4. Optionally set *manual* portion factors for both people; default 1.0 preserves source quantities.
5. Review the shopping quantities, unresolved-ingredient checklist and nutrition coverage.
6. Save as **draft**, then **approve** it. Approving locks it to prevent unintended daily changes.
7. Download `.md`, `.csv` or `.json` shopping files and a nutrition audit JSON. These download buttons preview current UI choices; approve first for an authoritative weekly plan.

### Daily journal JSON and CLI exports

After approving the week:

```bash
python journal_core.py day --date 2026-11-10
python journal_core.py week shopping --start 2026-11-09 --format md
python journal_core.py week shopping --start 2026-11-09 --format csv --out outputs/shopping_2026-11-09.csv
python journal_core.py week nutrition --start 2026-11-09
```

The CLI `--out` exporter **refuses to overwrite an existing file**. The web app's download buttons are easiest for shopping use.

## Nutrition reference schema

By default, the module loads `config/nutrition_reference_starter.csv` (generic illustrative estimates; **not a verified nutrition database**). It has columns:

```text
ingredient,measurement_state,basis_unit,kcal,protein_g,carbs_g,fat_g,source
```

- All figures are per **100 g** if `basis_unit=g`, or **100 ml** if `basis_unit=ml`.
- Measurement states: `raw`, `cooked`, `drained`, `as_served`. Matching is exact after conservative name normalization.
- Unknown/composite ingredients and incompatible units are **excluded from numeric totals and reported**. Eggs/pieces are not silently converted into grams. Raw rice and cooked rice have separate estimates, and quantities are never combined in shopping exports.
- For a reviewed replacement CSV, put `NUTRITION_REFERENCE_FILE=/absolute/path/to/reviewed.csv` in `.env`. The USDA FoodData Central dataset (https://fdc.nal.usda.gov/) or verified German package labels can provide values; check serving basis before entry.

**Important:** Training-dependent macro targets, per-person daily caloric needs, validated food conversions, AI optimization of weekdays, and full consumption/training history are the **next implementation phase**. The current demo figures must not be used as a medical or sports-diet prescription.

## Troubleshooting and privacy

- Keep your six existing `.env` file path settings. This upgrade does not change them.
- Do not sync `journal_core.sqlite3` across devices using Syncthing while it's open. The journal database is local durable state.
- Back up the database before every upgrade; keep `data/`, `.env`, and private shopping exports out of Git.
- The planner only reads the six explicitly configured Markdown files; it does not scan the corporate or personal vaults.
- Some Markdown recipe images are remote, but this interface displays recipe text only. No agent or external API is invoked in the new modules.
- Streamlit and its dependencies may need internet to install. The planner itself operates locally after installation.

---

## v0.3 nutrition feature branch

See [`docs/NUTRITION_V03.md`](docs/NUTRITION_V03.md) for the **new USDA FoodData Central importer**, separate user-reviewed nutrition targets, manually selected activity for the second person, gated read-only portion recommendations and a shopping-list correction interface. This release **does not** ship verified nutrient records or personalized macro targets and does **not** make the existing `config/nutrition_reference_starter.csv` a verified source.
