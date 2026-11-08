# Core v0.3 — Verified nutrition and shopping review (feature branch)

This is a **feature-branch update for Core v0.2**. It reads the same six Markdown sources and **does not modify** `journal_v3.py`, `tools.py`, `.env`, `credentials.json`, the source Markdown files, your approved weekly menus, or the database schema. It adds a local reference CSV, per-person targets, and shopping decisions **under `data/state/`**, which must remain untracked.

## Current capabilities

- USDA FoodData Central **search**, manual FDC ID selection, and explicit nutrient import from **Foundation** and **SR Legacy**. Source IDs are retained. Never auto-selects a food based on a recipe phrase. Import only matches after checking preparation state and food identity.
- Explicit **package-label nutrition input** per 100 g or 100 ml, recorded with brand/barcode provenance. Useful for German supermarket items and coffee milk; the user must verify label units.
- Separate profile targets for two people on **rest / easy / moderate / long** days. The app does not estimate either person's energy needs; targets are user-reviewed inputs. Approximate kcal consistency check (4/4/9) catches obvious mistakes.
- Person A can opt into the CrewAI training calendar. **Person B does not inherit Person A's training**, unless explicitly opted in. Choose her daily activity separately and store it locally.
- Read-only **portion adjustment suggestions** bounded to ±15% for each meal, only when the whole day has complete verified nutrition coverage. Does not modify saved or approved menus; no automatic calorie expenditure guessed from training.
- **Shopping resolutions** in the local web app. Choose `skip` for optional items or `replace` with exact ingredient, amount, unit and state. Stored separately in `data/state/shopping_reviews/YYYY-MM-DD.json`; the CLI shopping export uses those saved decisions.
- No default to the old demonstrative `config/nutrition_reference_starter.csv` for normal use. If a verified reference does not exist, the app displays an informative setup message rather than invented totals.

### Not yet implemented

No full automatic meal-plan calorie optimizer, complete nutrient matching for all 120 recipes, raw-to-cooked grocery yields, person-specific measured training energy expenditure, or auto-acceptance of nutrition changes. Neither the USDA network API nor the Streamlit browser was exercised in the build environment; the API adapters were tested against offline representative records, and the Python sources passed compilation and tests. Do not treat an approximate macro calculation as a clinical diet prescription.

## Installation on the new feature branch

First **commit Core v0.2 on the current branch**, then:

```bash
cd ~/Documents/CrewAI-Journal/CrewAI_Journal
source .venv/bin/activate
git switch -c feature/nutrition-optimizer
```

Close Streamlit and back up the database and the v0.2 core source **outside the repository**:

```bash
BACKUP="$HOME/Documents/CrewAI-Journal/core-v02-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -a src/journal_core planner_app.py journal_core.py "$BACKUP/"
[ ! -f data/state/journal_core.sqlite3 ] || cp -a data/state/journal_core.sqlite3 "$BACKUP/"
```

Inspect archive contents before extracting:

```bash
unzip -l ~/Downloads/CrewAI_Journal_core_v0_3_update.zip
unzip -o ~/Downloads/CrewAI_Journal_core_v0_3_update.zip -d .
python journal_core.py check
python -m unittest discover -s tests -v
```

The ZIP overlays selected source/test files, creates `nutrition_setup.py` and the instructions/schema, but contains no personal profiles, verified food values, credentials or `.env`.

## USDA FoodData Central

Official docs: <https://fdc.nal.usda.gov/api-guide/>. Sign up for an API key there, then add this to your **untracked** `.env`:

```dotenv
FDC_API_KEY=YOUR_PRIVATE_DATA_GOV_API_KEY
# Optional; defaults to data/state/verified_nutrition.csv
# NUTRITION_REFERENCE_FILE=data/state/verified_nutrition.csv
```

A key is required for network calls. Check that `.env` is ignored by Git; don't paste keys into chat, logs, or commits.

Start the local web app:

```bash
streamlit run planner_app.py
```

Choose **Nutrition setup**. Search an English food name, compare candidate FDC records, enter its ID and the **exact matching recipe ingredient name**, choose raw/cooked/etc., confirm and import. Branded FDC records are intentionally excluded because their serving basis requires extra checks. API search uses the official `/foods/search` endpoint and import fetches `/food/{fdcId}`. Network access occurs only from your machine when you click the buttons. An unsuccessful lookup never writes the reference CSV.

CLI equivalent:

```bash
python nutrition_setup.py fdc search 'bananas raw'
python nutrition_setup.py fdc import --id <VERIFIED_ID> --ingredient banana --state as_served
python nutrition_setup.py reference status
```

For German branded groceries, use the **Verified local product label** form. Verify nutritional values per 100 g or 100 ml, brand/barcode, and source. The reference file, including sources, stays private in `data/state/verified_nutrition.csv`.

**Licensing:** USDA FoodData Central is CC0/public domain; cite USDA and retain FDC IDs. Open Food Facts is a separate project with ODbL obligations and variable crowdsourced data; v0.3 does not silently merge OFF data.

## Individual targets and training-linked activity

Open **Nutrition setup → Individual nutrition targets**. Set, for each person, four explicit daily energy/protein/carbohydrate/fat targets for rest, easy, moderate and long days. Review with a qualified professional when appropriate, especially for high training loads or dietary restrictions. No targets are prepopulated; do not copy illustrative values from another person.

**Me** may use the `Master Training.md` and `Master Gym.md` calendar. Preparation weeks P1–P4 are classified `easy` except Monday (`rest`). Standard weeks classify weekends `long` and Tue/Thu `moderate`; these are **simple planning categories**, not measured expenditure or a promise that you completed a session. Pauses and changed sessions need review.

**Wife** defaults to independent activity selection, so the app will not assume that she did your workouts. Save her own per-date activity classification in Nutrition setup. You can configure both profiles independently. Data is stored in:

- `data/state/nutrition_profiles.json`
- `data/state/manual_activity_loads.json`

An advanced option is `python nutrition_setup.py profiles import --file /path/to/your-reviewed-profile.json`; the expected JSON structure is in `config/nutrition_profiles.schema.json`.

## Shopping review

After selecting seven recipes in each of the four categories, open **Weekly meals → Resolve shopping list ingredients**. It displays unresolved ingredients for that week. Each row supports:

- **pending** — unresolved, excluded from trusted shopping totals.
- **skip** — explicitly excluded, e.g. an unwanted optional ingredient.
- **replace** — choose one real ingredient, one quantity **as written for that person before scaling**, a supported unit (`g`, `kg`, `ml`, `l`, `un`) and an explicit `raw`, `cooked`, `drained`, or `as_served` state.

Click **Save shopping resolutions**, then reload the app. The list recalculates. Approved meals are unchanged; decisions can be reset for the week. Do not treat the list as final until you manually reconcile raw vs cooked shopping quantities, ingredient alternatives, overlapping bases, perishables and pantry stock. The original recipe catalogs sometimes specify cooked lunch weights and raw dinner weights; the program does **not** invent conversion yields.

The CLI respects saved shopping decisions:

```bash
python journal_core.py week shopping --start 2026-11-09 --format md
```

## Portion proposals and safety

When all recipe ingredients and the coffee milk have **complete verified nutrient mappings**, choose a day/person under **Weekly meals → Training-aware portion proposal**. The read-only optimizer tries small (±15%) multipliers for breakfast/lunch/dinner/snacks and compares approximate macro totals to that person's configured target. It will display **blocked** if anything is missing. The suggestions are **not saved or applied**, are not meal substitutions, and should be reviewed for appropriate servings, fueling during long sessions, allergies and digestive tolerance.

The first milestone is **traceable nutrition data and review controls**. A later iteration can build an approved week-level optimization workflow and raw-purchase conversion factors only after the ingredient reference and target profiles have been checked.

## Verification

```bash
python -m py_compile planner_app.py nutrition_setup.py
python -m unittest discover -s tests -v
python nutrition_setup.py reference status
```

Expected locally: 23 offline tests (unless you add more). Source files are parsed without network/agents. The browser UI and real API calls still need a manual check on the ThinkPad.

## Git safety

Always leave `.env`, `credentials.json`, `token.json`, `data/`, local shopping exports and the private profile/reference JSON/CSV files out of Git. Check current tracked files with `git ls-files` before staging. Commit source code, docs, tests and the **empty schema only** in `feature/nutrition-optimizer`.
