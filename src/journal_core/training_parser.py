"""Deterministic parser for supplied triathlon and gym Markdown layouts.

Only displays prescribed source text. Does not infer a start date or advance weeks.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import re
from .models import DailyTraining
from .paths import training_paths

DAY_KEYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PHASES = [
    (1, 12, "foundation"), (13, 24, "base"), (25, 36, "build"),
    (37, 44, "race_specific"), (45, 48, "peak"),
    (49, 50, "taper"), (51, 51, "race"), (52, 52, "recovery"),
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\*\*|`", "", text)).strip()


def _cells(line: str) -> list[str]:
    if not line.strip().startswith("|"):
        return []
    c = [_clean(v) for v in line.strip().strip("|").split("|")]
    if not c or all(re.fullmatch(r":?-{2,}:?", x) for x in c):
        return []
    return c


def _between(text: str, start_pattern: str, end_pattern: str) -> str:
    start = re.search(start_pattern, text, re.M)
    if not start:
        raise ValueError(f"Missing expected heading: {start_pattern}")
    tail = text[start.end():]
    end = re.search(end_pattern, tail, re.M)
    return tail[:end.start()] if end else tail


def _first_table(section: str) -> tuple[list[str], list[list[str]]]:
    in_table = False
    headers: list[str] = []
    data: list[list[str]] = []
    for line in section.splitlines():
        cells = _cells(line)
        if cells:
            if not in_table:
                in_table, headers = True, cells
            elif len(cells) == len(headers):
                data.append(cells)
        elif in_table:
            if re.match(r"^\s*\|[\s:|\-]+\|\s*$", line):
                continue  # Markdown table divider, not end of table
            break
    if not headers or not data:
        raise ValueError("Expected Markdown table with data rows")
    return headers, data


def _day(cell: str) -> str | None:
    for day in DAY_KEYS:
        if re.match(rf"^{day}\b", cell, re.I):
            return day
    return None


class TrainingCatalog:
    def __init__(self, training_path: Path, gym_path: Path):
        self.training_path, self.gym_path = training_path, gym_path
        self.training_text = training_path.read_text(encoding="utf-8")
        self.gym_text = gym_path.read_text(encoding="utf-8")
        self.prep = self._prep()
        self.main = self._main()
        self.race = self._special(51)
        self.recovery = self._special(52)
        self.gym_days = self._gym_days()
        self.gym_prep = self._gym_prep()
        self.gym_exercises = self._gym_exercises()
        self.gym_phases = self._gym_phases()
        if set(self.prep) != {f"P{i}" for i in range(1, 5)}:
            raise ValueError(f"Expected P1–P4; got {list(self.prep)}")
        if set(self.main) != set(range(1, 51)):
            raise ValueError(f"Expected training weeks 1–50; got {len(self.main)}")
        if set(self.gym_days) != set(DAY_KEYS):
            raise ValueError("Gym timetable needs all 7 weekdays")

    def _prep(self) -> dict[str, dict[str, dict[str, str]]]:
        plans = {}
        for m in re.finditer(r"^### Preparation Week (P[1-4])\b.*$", self.training_text, re.M):
            tail = self.training_text[m.end():]
            cutoff = re.search(r"^#{2,3}\s+", tail, re.M)
            section = tail[:cutoff.start()] if cutoff else tail
            headers, rows = _first_table(section)
            week = {}
            for cells in rows:
                day = _day(cells[0])
                if day:
                    week[day] = {headers[i]: value for i, value in enumerate(cells)}
            if set(week) != set(DAY_KEYS):
                raise ValueError(f"Missing days in {m.group(1)}: {set(DAY_KEYS)-set(week)}")
            plans[m.group(1)] = week
        return plans

    def _main(self) -> dict[int, dict[str, str]]:
        section = _between(self.training_text, r"^## 5\. Week-by-week 52-week cycle.*$", r"^### Week 51\b")
        rows = {}
        headings = ["week", "tue_bike", "wed_swim", "thu_run", "fri_bike", "sat_bike_brick", "sun_run", "total"]
        for line in section.splitlines():
            cells = _cells(line)
            if len(cells) != 8:
                continue
            m = re.match(r"^(\d{1,2})(?:\b|\s)", cells[0])
            if m and 1 <= int(m.group(1)) <= 50:
                week = int(m.group(1))
                if week in rows:
                    raise ValueError(f"Duplicate main training week {week}")
                rows[week] = dict(zip(headings, cells))
        return rows

    def _special(self, week: int) -> dict[str, dict[str, str]]:
        heading = rf"^### Week {week} — .*"
        section = _between(self.training_text, heading, r"^#{2,3}\s+")
        headers, rows = _first_table(section)
        expanded = {}
        for cells in rows:
            name = cells[0]
            for day in DAY_KEYS:
                if re.search(rf"\b{day}\b", name, re.I):
                    expanded[day] = {headers[i]: value for i, value in enumerate(cells)}
            # Covers 'Mon–Tue', 'Thu–Fri', 'Sat–Sun' and single-day entries.
            m = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[–-](Mon|Tue|Wed|Thu|Fri|Sat|Sun)", name)
            if m:
                a, b = DAY_KEYS.index(m.group(1)), DAY_KEYS.index(m.group(2))
                for day in DAY_KEYS[a:b+1]:
                    expanded[day] = {headers[i]: value for i, value in enumerate(cells)}
        if set(expanded) != set(DAY_KEYS):
            raise ValueError(f"Missing race/recovery weekdays in W{week}: {set(DAY_KEYS)-set(expanded)}")
        return expanded

    def _gym_days(self) -> dict[str, dict[str, str]]:
        section = _between(self.gym_text, r"^## 2\. Integrated weekly timetable.*$", r"^## 3\.")
        headers, rows = _first_table(section)
        result = {}
        for cells in rows:
            d = _day(cells[0])
            if d:
                result[d] = dict(zip(headers, cells))
        return result

    def _gym_prep(self) -> dict[str, dict[str, str]]:
        section = _between(self.gym_text, r"^## 6\. Four-week preparation.*$", r"^## 7\.")
        headers, rows = _first_table(section)
        return {cells[0].upper(): dict(zip(headers, cells)) for cells in rows if re.fullmatch(r"P[1-4]", cells[0], re.I)}

    def _gym_exercises(self) -> dict[str, list[dict[str, str]]]:
        result = {}
        for which, section_num in (("A", 3), ("B", 4)):
            section = _between(self.gym_text, rf"^## {section_num}\. Strength {which}.*$", rf"^## {section_num+1}\.")
            headers, rows = _first_table(section)
            result[which] = [dict(zip(headers, cells)) for cells in rows]
        return result

    def _gym_phases(self) -> list[tuple[range, str]]:
        section = _between(self.gym_text, r"^## 7\. Main 52-week strength periodization.*$", r"^## 8\.")
        _, rows = _first_table(section)
        result = []
        for line in rows:
            match = re.match(r"^(\d+)\s*[–-]\s*(\d+)", line[0])
            if match:
                result.append((range(int(match.group(1)), int(match.group(2))+1), " | ".join(line[1:])))
            else:
                match = re.match(r"^(\d+)\b", line[0])
                if match:
                    result.append((range(int(match.group(1)), int(match.group(1))+1), " | ".join(line[1:])))
        return result

    def preview(self, on_date: date, week_code: str) -> DailyTraining:
        week_code = str(week_code).strip().upper().removeprefix("W") if not str(week_code).upper().startswith("P") else str(week_code).upper()
        if not (re.fullmatch(r"P[1-4]", week_code) or (week_code.isdigit() and 1 <= int(week_code) <= 52)):
            raise ValueError("Week must be P1–P4 or 1–52")
        weekday = DAY_KEYS[on_date.weekday()]
        gym_data = self.gym_days[weekday]
        gym_morning = gym_data.get("Morning at home", "")
        notes = []
        optional = weekday == "Fri"
        if week_code.startswith("P"):
            phase = "preparation"
            day_data = self.prep[week_code][weekday]
            endurance = next((v for k,v in day_data.items() if any(t in k.lower() for t in ("endurance", "lunch /", "lunch/"))), "")
            morning = next((v for k,v in day_data.items() if "morning" in k.lower()), "")
            if weekday == "Tue":
                adjustment = self.gym_prep[week_code].get("Tuesday Strength A", "")
            elif weekday == "Thu":
                adjustment = self.gym_prep[week_code].get("Thursday Strength B", "")
            else:
                adjustment = self.gym_prep[week_code].get("Wed/Fri/Sat/Sun morning routines", "")
            notes.append("Use the P-week reduction, not standard full-cycle gym sets")
        else:
            number = int(week_code)
            phase = next(label for first,last,label in PHASES if first <= number <= last)
            if number <= 50:
                data = self.main[number]
                mapping = {"Mon": "Rest", "Tue": data["tue_bike"], "Wed": data["wed_swim"],
                           "Thu": data["thu_run"], "Fri": data["fri_bike"],
                           "Sat": data["sat_bike_brick"], "Sun": data["sun_run"]}
                desc = {"Mon": "Rest", "Tue": "Bike", "Wed": "Swim", "Thu": "Run",
                        "Fri": "Optional easy bike", "Sat": "Long bike + optional brick", "Sun": "Long run"}
                endurance = f"{desc[weekday]}: {mapping[weekday]}"
                morning = gym_morning
                adjustment = next((description for span,description in self.gym_phases if number in span), "")
                if weekday == "Fri" and data["fri_bike"].strip() in ("—", "-"):
                    endurance = "Rest from cardio (no Friday bike scheduled)"
                if number % 4 == 0 and number <= 44:
                    notes.append("Recovery/deload week: reduce strength volume as specified in gym plan")
            else:
                source = self.race if number == 51 else self.recovery
                special = source[weekday]
                endurance = special.get("Session", "")
                if not endurance:
                    endurance = next((v for k,v in special.items() if k != "Day"), "")
                morning = "No structured loaded gym"
                adjustment = "No loaded gym in race/recovery weeks"
                if "Notes" in special:
                    notes.append(special["Notes"])
        if weekday == "Tue":
            workout = "Strength A"
            exercises = self.gym_exercises["A"] if phase not in {"race", "recovery"} and week_code != "50" else []
        elif weekday == "Thu":
            workout = "Strength B"
            exercises = self.gym_exercises["B"] if phase not in {"race", "recovery", "taper"} else []
        else:
            workout, exercises = None, []
        if week_code in {"49", "50", "51", "52"}:
            notes.append("Taper/race/recovery rules override the standard gym schedule")
            if week_code in {"50", "51", "52"}:
                workout, exercises = None, []
            if week_code == "49" and weekday != "Tue":
                workout, exercises = None, []
        if weekday == "Mon":
            workout, exercises = None, []
        return DailyTraining(
            date=on_date.isoformat(), weekday=weekday, week=week_code,
            phase=phase, endurance=endurance, morning=morning,
            gym_workout=workout, gym_progression=adjustment,
            gym_exercises=exercises, optional=optional,
            sources={"training": str(self.training_path), "gym": str(self.gym_path)},
            notes=notes,
        )


def load_training() -> TrainingCatalog:
    return TrainingCatalog(*training_paths())
