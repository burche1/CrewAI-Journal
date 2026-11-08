"""Calendar-anchored training weeks. Reading dates never mutates training state."""
from __future__ import annotations
from datetime import date, timedelta
from .state import connect, utc_now

CYCLE = [f"P{i}" for i in range(1, 5)] + [str(i) for i in range(1, 53)]


def normalize_week(value: str) -> str:
    raw = str(value).strip().upper()
    if raw.startswith('W'):
        raw = raw[1:]
    if raw not in CYCLE:
        raise ValueError('Training week must be P1–P4 or W1–W52')
    return raw


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def anchor_training(start: date, week: str = 'P1', *, note: str = '') -> dict:
    if start.weekday() != 0:
        raise ValueError('The training start date must be a Monday')
    week = normalize_week(week)
    with connect() as cx:
        cx.execute('''INSERT INTO training_schedule (id,anchor_date,anchor_week,paused_at,paused_week,updated_at)
            VALUES (1,?,?,NULL,NULL,?) ON CONFLICT(id) DO UPDATE SET
            anchor_date=excluded.anchor_date,anchor_week=excluded.anchor_week,
            paused_at=NULL,paused_week=NULL,updated_at=excluded.updated_at''',
            (start.isoformat(),week,utc_now()))
        cx.execute('''INSERT INTO training_schedule_events (action,effective_date,week_code,note,created_at)
            VALUES ('anchor',?,?,?,?)''', (start.isoformat(), week, note, utc_now()))
    return {'start': start.isoformat(), 'week': week, 'mode': 'automatic', 'note': note}


def get_schedule() -> dict | None:
    with connect(create=False) as cx:
        if cx is None:
            return None
        if not cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='training_schedule'").fetchone():
            return None
        row = cx.execute('''SELECT anchor_date,anchor_week,paused_at,paused_week
                            FROM training_schedule WHERE id=1''').fetchone()
    if not row:
        return None
    return dict(zip(('anchor_date','anchor_week','paused_at','paused_week'),row))


def week_for_date(on_date: date) -> dict | None:
    schedule = get_schedule()
    if not schedule:
        return None
    start = date.fromisoformat(schedule['anchor_date'])
    if on_date < start:
        raise ValueError(f'Training has not started; anchor date is {start.isoformat()}')
    if schedule['paused_at'] and on_date >= date.fromisoformat(schedule['paused_at']):
        return {'week': schedule['paused_week'], 'source': 'paused', 'anchor': schedule['anchor_date'],
                'paused_at': schedule['paused_at'], 'complete': False}
    index = CYCLE.index(schedule['anchor_week']) + ((monday(on_date) - start).days // 7)
    complete = index >= len(CYCLE)
    return {'week': CYCLE[min(index, len(CYCLE)-1)], 'source': 'calendar',
            'anchor': schedule['anchor_date'], 'complete': complete}


def pause_training(on_date: date, note: str = '') -> dict:
    info = week_for_date(on_date)
    if not info:
        raise ValueError('Start automatic progression with training schedule first')
    if info['source'] == 'paused':
        return info
    paused_at = monday(on_date)
    with connect() as cx:
        cx.execute('''UPDATE training_schedule SET paused_at=?,paused_week=?,updated_at=? WHERE id=1''',
                   (paused_at.isoformat(),info['week'],utc_now()))
        cx.execute('''INSERT INTO training_schedule_events (action,effective_date,week_code,note,created_at)
          VALUES ('pause',?,?,?,?)''', (paused_at.isoformat(), info['week'],note,utc_now()))
    return week_for_date(on_date)


def resume_training(on_date: date, *, week: str | None = None, note: str = '') -> dict:
    schedule = get_schedule()
    if not schedule or not schedule['paused_at']:
        raise ValueError('Training schedule is not paused')
    if monday(on_date) < date.fromisoformat(schedule['paused_at']):
        raise ValueError('Resume date cannot precede pause date')
    if on_date.weekday() != 0:
        raise ValueError('Resume date must be a Monday')
    chosen = normalize_week(week or schedule['paused_week'])
    return anchor_training(on_date, chosen, note=f'Resume. {note}'.strip())
