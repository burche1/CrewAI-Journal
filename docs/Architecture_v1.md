# CrewAI Journal — Proposed Architecture v1.0

**Status:** Design specification; no implementation is implied.  
**Basis:** Current `journal_v3.py`, `tools.py`, and the six supplied Markdown catalogs/plans (Breakfast, Lunch, Dinner, snacks, Master Gym, Master Training).  
**Principle:** Python handles source retrieval, parsing, selection, calculations, validation, state and rendering. CrewAI is responsible for optional editorial reasoning and well-bounded narration, never for silently changing source facts.

## A. Product and scope

### Daily edition, in display order
1. **Weather:** daily synopsis, high/low, rain risk, relevant hourly forecast; retain existing Open-Meteo-based logic initially, but verify date, time zone, errors and rendering.
2. **News:** usually 4–8 sourced metadata-based articles (title, summary/description, source, published date, permalink, topic), favoring *new-to-the-reader* recent items. If insufficient new items, use explicitly labeled archive context with documented dates; never invent events or claim full-article verification from metadata alone.
3. **Personal agenda:** disabled for now. No automatic Google or corporate-vault access until explicitly authorized and tested.
4. **Today’s training:** original triathlon session, strength/mobility session, phase/week, load, optionality, relevant guidance; keep plan text provenance.
5. **Today’s food:** approved weekly plan’s breakfast, lunch, dinner and suitable snacks, individual portions for each person; retain cooking/storage notes; macros only when backed by validated data.
6. **Chess:** daily puzzle, side to move and objective; show the correct solution at the *end of the entire journal*.
7. **Sudoku:** puzzle with validated unique solution and human-logic solvability; increase difficulty across the week, hardest on Sunday by techniques rather than simply clue count.
8. **Reading:** a ~15-minute excerpt (configurable, usually about 2,000–3,000 words depending on reading speed) ending at a paragraph or convenient section boundary; do not advance reading position when merely generating or previewing the edition.
9. **Chess solution:** placed last, independently rendered from validated chess moves.

### On-demand modes
- `journal preview --date YYYY-MM-DD`: collect or use cached inputs as configured, assemble draft; never commit progress or shown-article ledger.
- `journal build --date YYYY-MM-DD`: produce an idempotent draft/snapshot and PDF. Repeating a build uses the same approved plan and reserved story set unless the user explicitly refreshes.
- `journal publish --date YYYY-MM-DD`: atomically mark the edition published and write shown-news entries; avoid double counts.
- `journal reading complete --date YYYY-MM-DD`: commit the reading bookmark once the excerpt was actually read.
- `journal training log ...`: record actual workout completed/skipped/adjusted (not just scheduled).
- `journal week plan --start YYYY-MM-DD`: interactive recipe selection and preview; then approve and persist.

Commands above are **proposed interfaces**, not implemented commands.

## B. Data-source boundaries

| Source | Access | Output | Writes allowed |
|---|---|---|---|
| `TRAINING_PLAN_FILE` | Read-only Markdown | Plan weeks and daily endurance prescriptions | Never |
| `GYM_PLAN_FILE` | Read-only Markdown | Strength A/B, mobility, periodization | Never |
| Four `*_INVENTORY_FILE` paths | Read-only Markdown | 120 recipe records | Never |
| NewsCollector v0.8.x | Restricted JSON CLI adapter | Catalog, batch collection receipts, multilingual search hits | NewsCollector alone writes its SQLite |
| Open-Meteo | HTTP client | Weather forecast and timestamps | Local cache only |
| Lichess | HTTP client | One daily puzzle and its solution | Local cache only |
| Books folder | Read-only ebook access | Structured chapters/paragraphs | Reading bookmark in Journal state only |
| Google / corporate Obsidian notes | Disabled until reauthorized | Later: limited calendar/briefing | No source file writes |

**Separation:** NewsCollector's `news.db` is not the Journal database. CrewAI Journal calls its public structured JSON interface, not direct SQL. Google credentials, OAuth tokens, personal documents and private notes are not in the Git repo or LLM prompt context by default. A synced mirror is not a security boundary; mount/allowlist only approved paths.

## C. Canonical deterministic pipeline

```
Input: date + timezone + approved profile + current weekly plan + catalog versions
    |
    +--> WeatherClient --------------------> WeatherSnapshot
    +--> NewsCollectorAdapter -------------> NewsCandidate[] -> NewsSelector -> NewsEdition[]
    +--> TrainingPlanParser + GymParser ----> DailyTrainingPlan
    +--> WeeklyPlanStore + RecipeCatalog --> DailyMealPlan (per person)
    +--> LichessClient ---------------------> ChessPuzzleSnapshot
    +--> SudokuGenerator + LogicSolver ----> SudokuSnapshot
    +--> BookParser + ReadingSelector -----> ReadingExcerptSnapshot
    |
    +--> DailyJournalSnapshot (Pydantic-validated, immutable by default)
              |
              +--> Optional small CrewAI editorial tasks (news context / introductions)
              |     with source-linked bounded inputs and strict output models
              |
              +--> Jinja2/Markdown renderer (escapes unsafe HTML)
                        |
                        +--> outputs/markdown/YYYY-MM-DD.md
                        +--> outputs/pdf/YYYY-MM-DD.pdf
                        +--> issue metadata + render log
```

**Rule:** LLM output is not allowed to change numeric recipe quantities, dated events, workout prescriptions, puzzle answers, reading text, source URLs, or provenance fields. Editorial text is attached in separate fields and can be omitted if a model fails.

## D. Proposed Python package

```
CrewAI_Journal/
  journal_v3.py                 # temporary legacy file, preserved during migration
  tools.py                      # temporary legacy file, preserved during migration
  settings.py                   # portable env paths; refactor later into config/settings.py
  config/
    journal.yaml                # sections enabled, timezone, language, rendering, topic weights
    news_policy.yaml            # publishers, collection jobs, topic interests, freshness, diversity
    profiles.yaml               # two people: explicit, consented per-person parameters/goals
  src/journal/
    cli.py                      # preview/build/publish/plan/record commands
    models.py                   # Pydantic contracts
    orchestration.py            # daily pipeline, never hardcoded absolute paths
    catalogs/
      markdown_reader.py         # content hashing, headings, source line references
      recipe_parser.py          # four recipe catalogs; ingredient normalization/ambiguities
      training_parser.py        # prep P1–P4 + W1–W52 tables and gym section mapping
      book_parser.py            # chapter/paragraph-aware TXT/EPUB/PDF extractors
    planners/
      training_calendar.py      # current phase/week/day and readiness gates
      weekly_meals.py           # interactive selection, draft, approval
      portion_optimizer.py      # individually adjusted servings once nutrition data validated
      shopping_list.py          # ingredient aggregation + unresolved-item report
      news_selector.py          # topic scoring, recency, diversity, show-history
      reading_selector.py       # paragraph/chapter windows near target reading time
    integrations/
      newscollector.py          # versioned subprocess JSON bridge (no shell=True)
      weather.py
      lichess.py
    puzzles/
      sudoku.py                 # uniqueness + human-technique solving
      chess.py                  # reconstruct FEN, validate solution
    memory/
      repository.py             # journal SQLite, transactions, migrations
    agents/
      news_editor.py            # bounded editorial synthesis, optional
      meal_editor.py            # optional nonnumeric descriptions/reordering proposals
      final_editor.py           # optional introductions, not raw content rewrite
    rendering/
      pdf.py
      templates/               # Jinja + CSS; local assets
  data/
    journal.sqlite             # private persistent state (Git ignored)
    cache/                     # HTTP and source snapshots
    plans/                     # approved weekly menus in JSON for export/backups
  outputs/
    markdown/
    pdf/
  Books/                        # user-supplied source files, Git ignored
  tests/
  docs/
    ARCHITECTURE.md
    DATA_CONTRACTS.md
```

## E. Source-specific parsers (grounded in the supplied files)

### Training
- `Master Training.md`: **P1–P4** are tables by day. Main **W1–W50** are table rows for durations and weekly load; W51 race and W52 recovery have separate daily tables. Session interpretation also refers to Section 6, weekly schedule Section 3 and readiness checks Section 9. Do not use the old `Week X` heading extractor unchanged.
- `Master Gym.md`: day-of-week table maps Tue Strength A, Thu Strength B, Wed mobility C, Fri prehab D, weekend activation/mobility, Mon full rest. P1–P4 have specific set reductions; W1–W52 have phase-dependent dose rules.
- Persist `TrainingCycleState` with `phase`, `week`, `phase_start`, `confirmed_on`, `progression_decision`, and optional race date. Never increase a week on app startup, preview or a repeated Monday run.
- Persist `TrainingSessionLog` separate from schedule (planned vs completed, RPE, duration, distance, sets, repetitions, loads, notes, symptoms). Only advance progression after manual/approved weekly review.
- For incomplete or ambiguous source parsing, return `needs_review`, never silently substitute a generic workout.

### Recipes
- Exactly **30 recipes in each** supplied catalog: breakfast, lunch, dinner, snacks; IDs like `breakfast:01`, `lunch:02`, `dinner:01`, `snacks:11`.
- Each recipe uses a Markdown heading `### NN. Name`, per-person `**Você:**` and `**Esposa:**` lines, instructions, organization and potentially images/tags. Preserve entire original section and source hash for audit.
- The catalog states its weights differ: common **lunch** grains/proteins are cooked as specified, common **dinner** proteins/grains are raw unless otherwise stated, breakfast has **coffee plus 50 mL milk per person** beyond listed ingredients; snack whey is powder weight, not protein grams.
- Preserve each ingredient’s `quantity`, `unit`, `canonical_food_id`, `measurement_state` (raw/cooked/drained/as_served), optionality and `confidence`/`needs_clarification` flags. Do not merge `100 g raw rice` and `100 g cooked rice` without explicitly validated yield conversions. Composite ingredient choices (`pepper/zucchini`, generic `one fruit`, cooked composite dishes like `chili pronto`) must be resolved by user or reported as unresolved.
- Images are illustrative external links, not sources for macros or actual nutritional composition.
- Macro estimates require an explicit nutrient source and recipe normalization; original quantities are starting portions **not calculated macro prescriptions**.

## F. Weekly interactive meal planner

**Selection:** list all 30 recipes for each category with name, ingredients, time and prep/storage flags. User chooses **seven candidates per category** (7 breakfast, 7 lunch, 7 dinner, 7 snacks). This means 28 selected candidate recipes, not a requirement to consume exactly one snack daily. Meal/snack frequency and endurance fueling are determined by the approved plan and personal needs. No extra recipe is invented.

**Proposed flow:**
1. `catalog validate`: report parse coverage, ambiguous ingredients and missing units.
2. `week plan`: choose Monday start date; optionally import last week's selected IDs; use an interactive terminal menu (e.g. `questionary`/`rich`, with plain numbered-input fallback).
3. `week arrange`: Python proposes days based on source meal-prep tags and workout load; optional CrewAI proposal may reorder selected IDs **only**.
4. `week portion preview`: calculate individual factors from reviewed requirements/nutrient data; show original vs adjusted quantities and any unmet targets; if targets aren't configured, use original portions and label them `baseline`.
5. `week shopping`: sum **both people's** adjusted ingredients across all scheduled servings, include recurring additions (e.g. breakfast coffee milk) and packing/units; report unresolved items, pantry items and raw/cooked mismatch instead of falsifying exact totals.
6. `week approve`: explicit approval creates `data/plans/YYYY-MM-DD.json` and stores a versioned snapshot in SQLite, plus printable Markdown shopping list and CSV/JSON exports.
7. `journal build`: **only reads the approved plan** for that date. It does not ask the nutrition agent to choose new meals.

**Per-person boundaries:** training data currently describes one athlete; do not infer the other person's activities/energy expenditure. Individual goals, restrictions and measurement choices require separate settings. A validated calculator provides ranges/assumptions; a language model must not invent precision.

### Proposed approved week-plan document
```json
{
  "schema_version": "1.0",
  "week_start": "2026-11-09",
  "status": "approved",
  "source_catalog_hashes": {
    "breakfast": "sha256:...",
    "lunch": "sha256:...",
    "dinner": "sha256:...",
    "snacks": "sha256:..."
  },
  "selected_candidates": {
    "breakfast": ["breakfast:01", "breakfast:02", "breakfast:03", "breakfast:04", "breakfast:05", "breakfast:06", "breakfast:07"],
    "lunch": ["lunch:01", "lunch:02", "lunch:03", "lunch:04", "lunch:05", "lunch:06", "lunch:07"],
    "dinner": ["dinner:01", "dinner:02", "dinner:03", "dinner:04", "dinner:05", "dinner:06", "dinner:07"],
    "snacks": ["snacks:01", "snacks:02", "snacks:03", "snacks:04", "snacks:05", "snacks:11", "snacks:12"]
  },
  "days": {
    "2026-11-09": {
      "breakfast": "breakfast:01",
      "lunch": "lunch:02",
      "dinner": "dinner:01",
      "snacks": ["snacks:11"],
      "portions": {"person_a": "baseline", "person_b": "baseline"}
    }
  },
  "approved_at": "2026-11-08T15:00:00+01:00"
}
```
*Illustrative contract; no plan or quantities are calculated by this document.*

## G. NewsCollector editorial policy and memory

1. Maintain `config/news_policy.yaml`: prioritized topics, allowed source IDs, allowed API keyword searches and allowed named RSS feeds, allowed language expansion, `target_count=6`, `min_count=4`, `max_count=8`, default publication window, per-source and per-topic diversity limits, archive fallback policy.
2. Use NewsCollector `catalog` first to validate source IDs and allowed methods/feeds. Build selective `batch` requests **only for those configured jobs**, not an all-publisher sync on every run. Collect only if explicitly requested for the edition; write/keep collection results separately from search results.
3. Use `search` against the *unified NewsCollector database* (including historical articles) with multilingual topic expansion. Rank stored metadata using source provenance, publication time, title/description relevance, diversity and history of past display. Do not confuse ingestion time with publication time.
4. Track each shown article in Journal SQLite: canonical URL/article ID, issue date, topic, last shown, count, story mode. Reserve candidates in a draft snapshot; only mark `shown` when publishing. Repeated preview/build of the same issue cannot consume new items.
5. If no fresh unseen articles exist, display a clearly labeled **Archive** item, optionally with a brief *historical context* paragraph derived from multiple dated metadata records. Never claim a new event or present LLM extrapolation as a verified report. When only metadata is available, summaries are **publisher-provided descriptions or carefully grounded summaries of that metadata**, not summaries of paywalled/full text.
6. A local `refresh_news` action can invalidate an unapproved draft's news candidates, but not rewrite previously published issues.

### Example news policy (design proposal)
```yaml
news:
  target_count: 6
  min_count: 4
  max_count: 8
  recent_hours: 72
  max_per_publisher: 2
  fallback: labeled_archive
  topics:
    - {id: linux, weight: 3}
    - {id: technology, weight: 3}
    - {id: automotive, weight: 2}
    - {id: brazil, weight: 2}
    - {id: germany, weight: 2}
    - {id: gaming, weight: 1}
    - {id: sport, weight: 1}
  collection_jobs: []  # populate only after validating sources/feeds against catalog
```

The displayed IDs above are *editorial interests*, not guaranteed existing NewsCollector `topics.yaml` IDs. Map each to actual registered topic keys and verified collection actions before implementation. More topics can be added later without changing the adapter.

## H. Reading, chess and Sudoku

### Reading
- Support TXT, EPUB, and text-extractable PDF with format-specific parsers. EPUB should use ordered spine/chapter/paragraph identifiers; PDFs need text-quality checks and page offsets. Do not silently skip unreadable pages.
- Estimate read time by word count with a configurable user-specific reading speed. Aim near 15 minutes, but finish at a paragraph/section boundary; prefer convenient chapter ends when close to target, otherwise avoid enormous chapters.
- `BookProgress` stores content hash, chapter/paragraph marker, last **completed** excerpt and timestamps. `reading prepared` does not mutate the bookmark; `reading complete` commits it once. Rebuilding the same issue reuses its exact excerpt.
- Keep reading text from owned/authorized sources out of agent prompts when exact reproduction is needed; insert it directly in the renderer.

### Chess
- Fetch daily Lichess record once and cache by puzzle ID/date; reconstruct the position from game PGN and initial ply when a FEN isn't supplied. Validate each solution move with `python-chess`; present side-to-move and a theme-derived objective. Keep the solution secret until the final page/section.

### Sudoku
- Generate a valid complete grid, remove clues and assert **exactly one** solution using a backtracking solver.
- Additionally run a **human-logic technique solver** and retain an explanation trace. Only accept puzzles solved completely by the allowed techniques for the intended weekday. Count of clues is *not* a reliable difficulty/logic guarantee.
- Save seed, puzzle, solution, technique trace and difficulty for the issue; render puzzle without solution unless user chooses a separate answer key.

## I. Durable state and idempotency

Journal-owned SQLite (`data/journal.sqlite`) with migrations and controlled writes:
- `journal_issues` — date, status (`draft`, `published`), snapshot hash, render paths, schema version
- `news_appearances` — issue_id, article ID/url, first/last shown, editorial topic, archive flag
- `training_cycle` / `training_sessions` — confirmed phase/week and planned-versus-completed activities
- `recipe_catalog_versions` / `weekly_meal_plans` / `daily_meal_schedules` — approved selections and portions
- `book_progress` / `reading_excerpts` — prepared vs completed excerpts
- `puzzle_cache` / `weather_cache` — reproducible daily supporting material
- `run_events` — tool source, timestamp, outcome, data version/hash, duration, safe error message

**Transaction rules:** preview never updates progress; build creates/updates a draft idempotently; publish marks a single issue and its story ledger together; plan approval is explicit; retries of tool failures do not duplicate persistent updates. Store a consistent `Europe/Berlin` issue date plus timezone-aware UTC provenance timestamps.

## J. Representative normalized data contracts

### `DailyJournalSnapshot`
```json
{
  "schema_version": "1.0",
  "issue_date": "2026-11-09",
  "timezone": "Europe/Berlin",
  "status": "draft",
  "weather": {"status": "ok", "forecast_for": "2026-11-09", "data": {}},
  "news": {"status": "ok", "items": [], "collection_report": {}},
  "agenda": {"status": "disabled", "events": [], "highlights": []},
  "training": {"status": "needs_review", "phase": null, "week": null, "sessions": []},
  "meals": {"status": "not_planned", "week_start": null, "recipes": []},
  "chess": {"status": "ok", "puzzle": {}, "solution": {}},
  "sudoku": {"status": "ok", "puzzle": {}, "solution": {}},
  "reading": {"status": "ok", "excerpt": {}, "completed": false},
  "errors": [],
  "provenance": {}
}
```
All empty objects above are placeholders for **defined typed submodels**, not an invitation to omit their validation. Failures are explicitly indicated per section; one unavailable provider should not prevent a safe partial journal.

## K. Acceptance tests before first real daily issue

- Recipe parser finds **30 distinct recipes per catalog**, accurately captures both people's portions, cooking state, optional items and warnings; checks ID stability against the source hash.
- Training parser resolves **P1–P4 and W1–W52** including recovery, taper, gym dosage and days off; manual readiness confirmation is required to advance phases.
- Weekly planner selects 7 candidates per category, arranges 7 calendar days, persists the approved plan, and generates a shopping list with all recognized units plus explicit unresolved items.
- `preview` cannot update training week, reading bookmark, published-story history, or approved meal plan; rebuilding the same issue is deterministic with cached snapshots.
- NewsCollector mocked JSON agent calls distinguish collection from local search; returned titles/URLs/dates are present, deduped, source-linked and have no implicit full-text access. Archive fallback is labeled.
- Chess move sequence validates against reconstructed position; Sudoku has exactly one solution **and** passes configured human-logic solver.
- Weather time zone/date and transient outages are handled; PDF renders with missing optional sections and never mixes stale `/tmp` files across runs.
- Google and corporate-vault connectors remain disabled until reviewed and approved.

## L. Implementation order
1. **Contracts & state:** Pydantic models, `settings.py` extensions, SQLite schema, run IDs and CLI `preview` mode.
2. **Source parsers:** recipes 120/120, training/gym, book formats; source-hash validation and tests.
3. **Weekly planner:** interactive selection, deterministic weekday arrangement, approval and baseline shopping list with unresolved-item handling.
4. **Training/meal daily snapshot:** two-person daily display, completion logging, future individualized macro calculations after data normalization.
5. **NewsCollector adapter:** selective collection requests, multilingual search, article ranking, shown-story memory and archive fallback.
6. **Chess/Sudoku/reading:** reliable puzzle solutions, logical difficulty, exact excerpt bookmarking.
7. **Weather and renderer:** retain the current working design where possible; produce PDF plus Markdown from the same snapshot.
8. **CrewAI editorial tasks:** introduce only where they add value, with typed output and safe fallback.
9. **Google/agenda integration:** separate, later phase requiring permissions and access checks.

## M. Decisions needing explicit settings (not blockers for the architecture)
- Training cycle start week/date and whether/when race date will anchor W51.
- Whether the second person's workouts are available; until then, baseline portions/explicit goals only for that person.
- Approved nutrition reference source and preferred portion adjustment method.
- Default news source set and supported per-publisher collection jobs; map proposed interests to actual NewsCollector topic keys.
- Whether a reading bookmark advances only on a confirmed completion action (recommended) or on publication.
- Whether shopping-list pantry inventory will be maintained, or simply exported with an optional 'already have' checkbox.
