# Implementation status — v0.1

| Component | Status | Safety notes |
|---|---|---|
| Recipes: 4 Markdown catalogs, 120 entries | Implemented; tested | Source hashes and original text retained |
| Ingredients: initial tokenizer | Implemented; conservative | Do not treat as normalized shopping quantities |
| Training: P1–P4; W1–W50; race/recovery | Implemented; tested | Current week is explicit and manual |
| Gym: exercises, daily table, phase dose | Implemented; tested | Phase dose overrides standard exercise table |
| Weekly menu: terminal selection + draft/approval | Implemented; tested | Initially one chosen recipe/day/category |
| Daily training and meal JSON preview | Implemented; tested | No side effects |
| SQLite training/menu state | Implemented; tested | Local private file; no automatic progression |
| Macro calculation and personalized portions | Planned | Needs reliable nutrient inputs, person profiles and checks |
| Shopping list | Planned | Needs normalization including raw/cooked conversions |
| NewsCollector, news deduplication, archive | Planned | Separate subproject integration |
| Weather, chess, Sudoku, reading | Existing legacy implementation; not migrated yet | Independent validation needed |
| PDF and CrewAI editorial agents | Planned | Consume structured snapshots only |
| Google/Calendar/Drive/corporate notes | Disabled | Only enable on explicit permission/configuration |

Current output is **JSON preview**, not a finished newspaper.
