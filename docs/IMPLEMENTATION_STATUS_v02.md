# v0.2 Implementation Status

**Validated offline** against the 6 uploaded Markdown sources with 120 recipes and 56 training weeks.

Implemented: week progression derived by calendar; explicit pause/resume/reanchor; recipe picker GUI; approved weekly selections; per-person portion factor; shopping Markdown/CSV + unresolved list; optional per-ingredient reference for macro estimates; daily JSON; backward-compatible v0.1 SQLite schema migration.

Not implemented: macro target derivation for either person, training-energy expenditure, individualized per-day quantity optimization, ingredient choice resolution UI, precise cooked-to-raw shopping yield conversions, real completed-training logs, NewsCollector, chess/sudoku/book, existing weather/PDF integration and Google OAuth.

No network calls or CrewAI agents are invoked by the core. Browser planner implementation requires Streamlit installation on the user machine; automated tests cover underlying services, but UI was not end-to-end browser-tested in the build environment.
