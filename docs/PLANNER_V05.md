# CrewAI Journal Core v0.5 — Safe revisions, grocery choices and nutrition goals

## Summary

This is an **update on top of v0.4**, not a replacement of the whole CrewAI Journal. It updates only the local planner and its modules. It does not run CrewAI, contact Google, edit Markdown recipe sources, or touch the training or NewsCollector repositories.

### Weekly menu history

- Open **Weekly meals → Manage this week**.
- **Revise this week** archives the current approved/draft menu and shopping decisions, then unlocks the selections as a draft.
- **Restart from scratch** archives the current menu and saved shopping decisions, then removes the active plan for that Monday.
- **Restore archived selections** restores the selected earlier version **as a draft**, requiring a fresh review and approval. Original approved records remain archived; review choices must be checked again and are not silently applied to restored selections.
- History uses an additive `weekly_menu_history` SQLite table. Other weeks, training history and nutrition configurations are not affected.

### The ingredient resolution UI

The new **Resolve ingredients** panel separates:

1. **Mixed ingredients**, e.g. `250 g pimentão/abobrinha`: assign percentages summing to 100%; the original 250 g is shared across the selected products, for each person at that person's approved portion factor. A stored split applies to matching occurrences across the selected week.
2. **Alternatives**, e.g. `pão branco ou misto`: choose a named product instead of interpreting the slash as an automatic 50/50 mix.
3. **Fruit choices**, e.g. `1 fruta`: choose the actual fruit; unit quantities are aggregated and rounded for purchase *after* portion scaling.
4. **Optional items**: explicitly include or skip. Skipping means **not buying**, not removing it from the source recipe or its nutrition accounting.
5. **Prepared dishes and missing amounts**: provide a purchasable item or revise the source recipe to list actual components. A ready-made chili portion cannot be accurately turned into a list of raw beef, beans, and tomatoes without the recipe composition.

These shopping corrections are stored in a private weekly review JSON, not in the original recipe Markdown.

### Raw and cooked purchase weights

The new **Convert cooked/drained weights to raw purchases** section asks for the exact product and state (cooked, drained, or as-served) and a **reviewed weight yield**:

- Record `raw_g`: grams of raw/packaged ingredient actually purchased.
- Record `prepared_g`: grams of the *same ingredient* in the prepared state used by recipes.
- Enter the cooking method and a source (`weighed at home`, measured batch record, or a precisely identified published yield reference).
- The calculation then uses `raw_needed_g = prepared_needed_g * raw_g / prepared_g` and adds that raw quantity to other raw purchases of the same product and compatible unit.
- The approved factor is persisted in `data/state/food_yields.json`, and applied automatically on future shopping lists for the exact matching ingredient/preparation state.

No official default yields are automatically assigned. Water absorption, moisture loss, draining and preparation vary, so a single ratio for all rice, pasta, meat or vegetables would not be accurate. See [USDA Agriculture Handbook 102](https://www.ars.usda.gov/ARSUserFiles/80400530/pdf/ah102.pdf) and [USDA Food Buying Guide](https://foodbuyingguide.fns.usda.gov/home/about). Nutrient retention and yield are **separate calculations**; this feature handles *purchase weights*, not nutritional retention on cooking.

An ingredient state with no verified match remains flagged, including cooked-only ingredients. Source states such as `unknown` require editing/clarification before a conversion can be configured. `as_served` without a raw counterpart remains a provisional served-weight shopping estimate; peel/trimming and packaging yield may still matter.

### Nutrition goals (guided, user reviewed)

The old `Nutrition setup` tab is split into two clearer tabs:

- **Nutrition goals**: editable per-person weight, height, age, biological sex (for formula), ordinary non-training activity multiplier, weight direction, and adjustable additional energy for easy/moderate/long training days. It estimates resting energy using Mifflin–St Jeor and derives protein, fat and the remaining carbohydrate target. **Confirm before saving**. This is an estimate, **not** a prescribed diet or measured exercise expenditure.
- **Food reference**: optional USDA FoodData Central/verified food-label matching for recipe-level macro calculations. The reference starts empty, and you must match ingredients explicitly rather than accept fuzzy estimates. Food API access is only used when explicitly requested, using your private `.env` key.

The recipe catalogs supplied initial *pre-filled examples* of height, weight and age; those may be outdated and must be checked by both people. Only one person has the journal training schedule by default; the other person's activity can be selected separately for each day.

Nutrition targets are saved in `data/state/nutrition_profiles.json`, inputs in `data/state/nutrition_estimation_inputs.json`. Full training-aware automatic portion optimization is **not enabled**, because many original recipes still lack verified macro mappings and exact prepared-food composition; the bounded suggestion service remains advisory and blocked on incomplete nutrition coverage.

### Limits & safety

- No raw-to-cooked conversion is assumed without a reviewed ingredient-specific yield.
- No automatic mixed-food percentage split is invented from ambiguous source text.
- Shopping quantities are not equal to scientifically precise nutrient amounts.
- The Streamlit UI was syntax-checked, but the live web interface could not be tested in the build container because Streamlit is not installed there; validate on your ThinkPad.
- No personal profile, state, `.env`, original Markdown catalog, or authentication token is shipped in the update ZIP.

## Installation

1. Stop Streamlit (`Ctrl+C`).
2. Confirm you're on the feature branch and review `git status --short`.
3. Back up your code and entire `data/state` directory, because that folder contains approved menus, reviews, training anchors, personal profiles and cooking yields.
4. Inspect and extract `CrewAI_Journal_core_v0_5_update.zip` over v0.4.
5. Run `python -m unittest discover -s tests -v` and `streamlit run planner_app.py`.
6. Test revision/reset with a **test week** or with a carefully backed-up existing week. The source Markdown is unaffected.
