"""Local durable state with additive schema upgrades and no remote side effects."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from .models import WeeklyMenu
from .paths import database_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS training_schedule (
  id INTEGER PRIMARY KEY CHECK (id=1),
  anchor_date TEXT NOT NULL,
  anchor_week TEXT NOT NULL,
  paused_at TEXT,
  paused_week TEXT,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_schedule_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  effective_date TEXT NOT NULL,
  week_code TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_state (
  id INTEGER PRIMARY KEY CHECK (id=1),
  week_code TEXT NOT NULL,
  approved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS training_state_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_code TEXT NOT NULL,
  approved_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS weekly_menus (
  week_start TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('draft', 'approved')),
  selections_json TEXT NOT NULL,
  source_hashes_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect(*, create: bool = True):
    db = database_path()
    if not create and not db.is_file():
        yield None
        return
    if create:
        db.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(db)
    if create:
        # Recipe plans and individual nutrition-related notes are private local state.
        os.chmod(db, 0o600)
    try:
        cx.execute("PRAGMA foreign_keys = ON")
        if create:
            cx.executescript(SCHEMA)
            cols = {row[1] for row in cx.execute("PRAGMA table_info(weekly_menus)")}
            if "portion_factors_json" not in cols:
                cx.execute("ALTER TABLE weekly_menus ADD COLUMN portion_factors_json TEXT NOT NULL DEFAULT '{\"person_a\":1.0,\"person_b\":1.0}'")
        yield cx
        if create:
            cx.commit()
    except Exception:
        cx.rollback()
        raise
    finally:
        cx.close()


def set_week(week: str, note: str = "") -> None:
    timestamp = utc_now()
    with connect() as cx:
        cx.execute("INSERT INTO training_state (id,week_code,approved_at) VALUES (1,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET week_code=excluded.week_code, approved_at=excluded.approved_at",
                   (week, timestamp))
        cx.execute("INSERT INTO training_state_events (week_code,approved_at,note) VALUES (?,?,?)",
                   (week, timestamp, note))


def get_week() -> tuple[str, str] | None:
    with connect(create=False) as cx:
        if cx is None:
            return None
        return cx.execute("SELECT week_code,approved_at FROM training_state WHERE id=1").fetchone()


def save_menu(menu: WeeklyMenu) -> None:
    with connect() as cx:
        existing = cx.execute("SELECT status FROM weekly_menus WHERE week_start=?", (menu.week_start,)).fetchone()
        if existing and existing[0] == "approved":
            raise ValueError("Approved menu is locked; create an explicit revision workflow before changing it")
        cx.execute("""INSERT INTO weekly_menus (week_start,status,selections_json,source_hashes_json,updated_at,portion_factors_json)
                      VALUES (?,?,?,?,?,?) ON CONFLICT(week_start) DO UPDATE SET
                      status=excluded.status, selections_json=excluded.selections_json,
                      source_hashes_json=excluded.source_hashes_json, updated_at=excluded.updated_at,
                      portion_factors_json=excluded.portion_factors_json""",
                   (menu.week_start, menu.status, json.dumps(menu.selections, ensure_ascii=False),
                    json.dumps(menu.source_hashes), utc_now(), json.dumps(menu.portion_factors)))


def load_menu(week_start: str) -> WeeklyMenu | None:
    with connect(create=False) as cx:
        if cx is None:
            return None
        columns = {c[1] for c in cx.execute('PRAGMA table_info(weekly_menus)')}
        if not columns:
            return None
        additional = ',portion_factors_json' if 'portion_factors_json' in columns else ''
        row = cx.execute(f"SELECT week_start,status,selections_json,source_hashes_json,updated_at{additional} "
                         "FROM weekly_menus WHERE week_start=?", (week_start,)).fetchone()
    if not row:
        return None
    return WeeklyMenu(week_start=row[0], status=row[1], selections=json.loads(row[2]),
                      source_hashes=json.loads(row[3]), updated_at=row[4],
                      portion_factors=json.loads(row[5]) if len(row)>5 else {'person_a':1.0,'person_b':1.0})


def approve_menu(week_start: str) -> None:
    with connect() as cx:
        row = cx.execute("SELECT status FROM weekly_menus WHERE week_start=?", (week_start,)).fetchone()
        if not row:
            raise ValueError("No drafted menu for this week")
        if row[0] == "approved":
            return
        cx.execute("UPDATE weekly_menus SET status='approved', updated_at=? WHERE week_start=?",
                   (utc_now(), week_start))

# v0.5: audited, reversible weekly-plan management.
HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS weekly_menu_history (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_start TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('revise','reset','restore')),
  prior_status TEXT NOT NULL,
  selections_json TEXT NOT NULL,
  source_hashes_json TEXT NOT NULL,
  portion_factors_json TEXT NOT NULL,
  shopping_reviews_json TEXT NOT NULL,
  archived_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weekly_menu_history_week ON weekly_menu_history(week_start,version_id);
"""


def _archive_current(cx: sqlite3.Connection, week_start: str, action: str, reviews: dict) -> bool:
    row = cx.execute('''SELECT status,selections_json,source_hashes_json,portion_factors_json
                        FROM weekly_menus WHERE week_start=?''',(week_start,)).fetchone()
    if not row: return False
    cx.execute('''INSERT INTO weekly_menu_history
                  (week_start,action,prior_status,selections_json,source_hashes_json,
                   portion_factors_json,shopping_reviews_json,archived_at)
                  VALUES (?,?,?,?,?,?,?,?)''',
               (week_start,action,row[0],row[1],row[2],row[3],
                json.dumps(reviews,ensure_ascii=False),utc_now()))
    return True


def manage_menu(week_start: str, action: str) -> None:
    """Archive original menu plus reviews, then unlock or clear the week.

    Does not touch any training, nutrition, or other-week data.
    Existing menu content remains recoverable using restore_menu_version.
    """
    from .reviews import load_reviews, save_reviews
    from datetime import date
    if date.fromisoformat(week_start).weekday()!=0:
        raise ValueError('Week must begin on Monday')
    if action not in {'revise','reset'}:
        raise ValueError('Action must be revise or reset')
    reviews = load_reviews(week_start)
    with connect() as cx:
        cx.executescript(HISTORY_SCHEMA)
        if not _archive_current(cx,week_start,action,reviews):
            raise ValueError('No weekly menu for this date')
        if action == 'revise':
            cx.execute("UPDATE weekly_menus SET status='draft',updated_at=? WHERE week_start=?",
                       (utc_now(),week_start))
        else:
            cx.execute('DELETE FROM weekly_menus WHERE week_start=?',(week_start,))
    # Only current reviews are cleared; their previous values survive in history.
    save_reviews(week_start,{})


def list_menu_history(week_start: str) -> list[dict]:
    with connect() as cx:
        cx.executescript(HISTORY_SCHEMA)
        rows=cx.execute('''SELECT version_id,action,prior_status,archived_at
                           FROM weekly_menu_history WHERE week_start=? ORDER BY version_id DESC''',
                        (week_start,)).fetchall()
    return [{'version_id':r[0],'action':r[1], 'prior_status':r[2],'archived_at':r[3]} for r in rows]


def restore_menu_version(week_start: str, version_id: int) -> None:
    """Restore archived selections as a DRAFT; re-approval is required."""
    from .reviews import load_reviews, save_reviews
    reviews=load_reviews(week_start)
    with connect() as cx:
        cx.executescript(HISTORY_SCHEMA)
        row=cx.execute('''SELECT selections_json,source_hashes_json,portion_factors_json
                          FROM weekly_menu_history WHERE week_start=? AND version_id=?''',
                       (week_start,int(version_id))).fetchone()
        if not row: raise ValueError('Archived version not found for this week')
        _archive_current(cx,week_start,'restore',reviews)
        cx.execute('''INSERT INTO weekly_menus
                      (week_start,status,selections_json,source_hashes_json,updated_at,portion_factors_json)
                      VALUES (?,'draft',?,?,?,?)
                      ON CONFLICT(week_start) DO UPDATE SET status='draft',
                      selections_json=excluded.selections_json,
                      source_hashes_json=excluded.source_hashes_json,
                      updated_at=excluded.updated_at,
                      portion_factors_json=excluded.portion_factors_json''',
                   (week_start,row[0],row[1],utc_now(),row[2]))
    save_reviews(week_start,{})
