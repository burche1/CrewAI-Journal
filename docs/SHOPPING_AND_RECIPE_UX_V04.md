# CrewAI Journal — Grocery and recipe UI upgrade (Core v0.4)

This is a **non-destructive update over v0.3**. It does not update the legacy
`journal_v3.py`, `tools.py`, `.env`, credentials, approved weekly menus,
SQLite databases or Obsidian files.

## What changed

- **Picture cards**: each recipe is shown with the first HTTPS Markdown image,
  its name, source portion and Add/Remove action. The recipes remain in the
  configured `.md` files; the app never edits them. External photo hosts may
  require internet and can fail or track image requests. Disable the picture
  checkbox to stop rendering remote images.
- **Scalable catalog**: no 30-recipe limit; headings `### 01. Title` through
  `### 100. Title` and beyond are supported. IDs remain `breakfast:01`,
  `lunch:02`, etc. Add a new numbered recipe heading with exactly one `Você`
  and one `Esposa` line; duplicate numbers within a category are rejected.
- **Supermarket sections**: the shopping list uses typical German aisles such
  as `Obst & Gemüse`, `Brot & Backwaren`, `Käse, Eier & Molkerei` and others.
  Explicit, maintained aliases merge equivalent products such as coffee milk
  and ordinary milk, or filé de salmão and salmão.
- **Whole items**: eggs, apples and other `un` counts are aggregated for the
  *whole week* and rounded up for shopping. This does not alter recipe portions
  or produce exact nutritional estimates for fractional eggs.
- **Safe raw/cooked handling**: cooked rice, chicken and pasta are not silently
  added to raw purchase weights. Such items appear once with a state-by-state
  breakdown and a conversion warning. You must convert them based on your
  actual preparation yields before treating the list as final.
- **Simple ingredient review**: instead of a row for each person/day, review
  the ingredient *choice* once, applying it to repeated occurrences. Options:
  1. **Choose one ingredient** — keeps the individual source quantities.
  2. **Enter custom amount** — specifies the exact replacement and unit *per
     matching occurrence*, before approved portion factors.
  3. **Skip** — useful for optional ingredients or what is already on hand.
  The decisions are saved in the existing private weekly shopping review JSON,
  not written back into approved menus or Markdown files.
- **No long diagnostic output**: the Streamlit expression that accidentally
  displayed a `DeltaGenerator` object has been replaced with regular `if`
  statements. Raw audit JSON is available only through an advanced download.

## Install on the `feature/nutrition-optimizer` branch

1. Stop Streamlit (`Ctrl+C`).
2. Back up files and the local `data/state` directory before extraction.
3. From the repository root, extract the ZIP using `unzip -o`.
4. Run tests with `python -m unittest discover -s tests -v`.
5. Restart with `streamlit run planner_app.py` and refresh the browser.

## Review wizard example

`250 g pimentão/abobrinha` appears for both people. Choose the group,
select **Choose one ingredient**, pick `pimentao` (or `abobrinha`), then
**Save decision for all matching occurrences**. Its source quantities for
both people are preserved. The next run recalculates the grouped shopping
list and clears that choice from the unresolved list.

For `1 fruta`, type the desired exact fruit (e.g. `banana`) and keep
source unit counts. For an optional ingredient, choose **Skip** or enter
its actual name with the original quantity. For `chili pronto` made from
several components, you must either explicitly use the ready-made product
or resolve its ingredient recipe separately; the engine cannot infer the
raw shopping ingredients of an already cooked compound dish.

**Important:** A "review complete" message is not a nutritional endorsement,
and the supermarket list can still contain raw/cooked conversion warnings.

## Known limitations

- Aisle assignments and aliases are deliberately explicit. New ingredients
  can fall under `Sonstiges / Prüfen`; add them to the dictionary in
  `src/journal_core/grocery.py`. This is safer than silently fuzzy-merging
  distinct products.
- Raw/cooked purchase conversions are not implemented automatically.
- The review wizard resolves *one product per source expression*. For mixed
  ingredient amounts such as tomato + spinach, choose one ingredient or use
  explicit manual replacements; a split-percentage editor is future work.
- Recipe images remain links to external hosts; they are not downloaded or
  cached into the Git repository.
- The Streamlit interface was syntax checked and source inspected, but could
  not be browser-smoke-tested in the build environment because Streamlit was
  unavailable there. The Python business logic passed the complete test suite.
