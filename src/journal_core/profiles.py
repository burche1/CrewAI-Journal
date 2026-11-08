"""Explicit, per-person nutrition targets. No inferred medical or sport prescriptions."""
from __future__ import annotations
from datetime import date, timedelta
import json
import os
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
import settings
from .schedule import week_for_date
from .training_parser import load_training

LOADS = ('rest','easy','moderate','long')
PERSONS = ('person_a','person_b')

class MacroTarget(BaseModel):
    kcal: float = Field(gt=0, le=10000)
    protein_g: float = Field(gt=0, le=500)
    carbs_g: float = Field(ge=0, le=1500)
    fat_g: float = Field(ge=0, le=500)

    @model_validator(mode='after')
    def energy_consistency(self):
        theoretical = self.protein_g*4+self.carbs_g*4+self.fat_g*9
        if abs(theoretical-self.kcal) > max(250, 0.2*self.kcal):
            raise ValueError('Energy target inconsistent with protein/carbs/fat. Review targets (4/4/9 kcal/g approximate).')
        return self

class PersonProfile(BaseModel):
    label: str = Field(min_length=1,max_length=60)
    use_journal_training: bool = False  # Must be opted into separately for each person
    targets_by_load: dict[str,MacroTarget]

    @model_validator(mode='after')
    def all_loads(self):
        if set(self.targets_by_load) != set(LOADS):
            raise ValueError('Each person needs rest, easy, moderate and long day targets')
        return self

class NutritionProfiles(BaseModel):
    people: dict[str,PersonProfile]
    verified_by_user: bool = False
    notes: str = ''

    @model_validator(mode='after')
    def both_people(self):
        if set(self.people) != set(PERSONS):
            raise ValueError('Profiles must contain person_a and person_b')
        return self


def path() -> Path:
    return settings.JOURNAL_STATE_DIR / 'nutrition_profiles.json'


def load_profiles(file:Path|None=None) -> NutritionProfiles | None:
    file = Path(file) if file else path()
    return NutritionProfiles.model_validate_json(file.read_text(encoding='utf-8')) if file.is_file() else None


def save_profiles(profile:NutritionProfiles, file:Path|None=None)->Path:
    file = Path(file) if file else path()
    file.parent.mkdir(parents=True,exist_ok=True)
    staging=file.with_name(file.name+'.tmp')
    try:
        staging.write_text(profile.model_dump_json(indent=2), encoding='utf-8')
        os.chmod(staging,0o600)
        os.replace(staging,file)
    finally:
        staging.unlink(missing_ok=True)
    return file


def planned_load(on_date:date, *, week:str|None=None) -> dict:
    """Conservative categorization of *planned* training only.

    No calorie-expenditure estimation or assumed completed workouts.
    """
    if week is None:
        info=week_for_date(on_date)
        if not info or info.get('complete'):
            return {'load':None,'reason':'No active training week', 'week':None}
        week=info['week']
    preview=load_training().preview(on_date,week)
    if preview.phase in {'recovery','taper'}:
        load='rest' if on_date.weekday()==0 else 'easy'
    elif on_date.weekday()==0:
        load='rest'
    elif preview.phase=='preparation':
        load='easy'  # Re-entry is deliberately easy even on weekends
    elif on_date.weekday() in (5,6):
        load='long'
    elif on_date.weekday() in (1,3):
        load='moderate'
    else:
        load='easy'
    return {'load':load,'reason':'Calendar/day/plan phase heuristic, not measured effort',
            'week':preview.week, 'phase':preview.phase, 'endurance':preview.endurance}


def week_targets(start:date, profiles:NutritionProfiles) -> list[dict]:
    rows=[]
    for offset in range(7):
        on_date=start+timedelta(days=offset)
        rows.append({'date':on_date.isoformat(),
                     'persons':{person:target_for_person(profiles,person,on_date) for person in PERSONS}})
    return rows


def manual_loads_file()->Path:
    return settings.JOURNAL_STATE_DIR / 'manual_activity_loads.json'


def load_manual_load(person:str,on_date:date)->str|None:
    if person not in PERSONS:raise ValueError('Unknown person')
    file=manual_loads_file()
    if not file.is_file():return None
    entries=json.loads(file.read_text(encoding='utf-8'))
    value=entries.get(f'{person}|{on_date.isoformat()}')
    if value is not None and value not in LOADS:raise ValueError('Invalid stored activity load')
    return value


def save_manual_load(person:str,on_date:date,load:str)->Path:
    if person not in PERSONS or load not in LOADS:raise ValueError('Invalid person/activity load')
    file=manual_loads_file()
    file.parent.mkdir(parents=True,exist_ok=True)
    entries=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
    entries[f'{person}|{on_date.isoformat()}']=load
    tmp=file.with_name(file.name+'.tmp')
    try:
        tmp.write_text(json.dumps(entries,ensure_ascii=False,indent=2),encoding='utf-8')
        os.chmod(tmp,0o600)
        os.replace(tmp,file)
    finally:tmp.unlink(missing_ok=True)
    return file


def target_for_person(profile:NutritionProfiles,person:str,on_date:date,*,manual_load:str|None=None)->dict:
    if person not in PERSONS:raise ValueError('Unknown person')
    person_profile=profile.people[person]
    if person_profile.use_journal_training:
        result=planned_load(on_date)
        load=result['load']
        reason=result['reason']
    else:
        load=manual_load or load_manual_load(person,on_date)
        reason='Separately selected personal activity, not triathlon schedule'
    if load not in LOADS:
        return {'status':'needs_activity','person':person,'date':on_date.isoformat(),
                'reason':'Select this person’s activity load before assigning a target'}
    return {'status':'ready','person':person,'date':on_date.isoformat(),
            'load':load,'reason':reason,
            'target':person_profile.targets_by_load[load].model_dump()}
