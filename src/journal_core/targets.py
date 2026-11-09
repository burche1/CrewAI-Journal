"""Transparent estimate of individual nutrition *starting targets*, never prescriptions.

Only editable input values entered/approved in the UI are stored. Planned training
loads are categorical; no exercise calories are inferred from training minutes.
"""
from __future__ import annotations
from pathlib import Path
import json, os, math
import settings
from .profiles import LOADS, NutritionProfiles


def estimate_person(*,weight_kg:float,height_cm:float,age:int,sex:str,
                    background_multiplier:float=1.4,objective_delta_kcal:float=0.0,
                    training_additions:dict|None=None,
                    protein_g_per_kg:float=1.6,fat_g_per_kg:float=0.8)->dict:
    """Mifflin-St Jeor resting estimate; editable energy increments, not calorie burn.

    Kcal, protein, fat and residual carbohydrate targets are *estimates*.
    Applies energy additions to the specified background estimate, not additional
    activity multiplier, to prevent adding the same sport session twice.
    """
    if not 25<=weight_kg<=300 or not 120<=height_cm<=230 or not 18<=age<=100:
        raise ValueError('Review height, weight and age')
    if sex not in {'male','female'}:raise ValueError('Select biological sex for this formula')
    if not 1.1<=background_multiplier<=1.9:raise ValueError('Background factor outside supported interval')
    if not -750<=objective_delta_kcal<=750:raise ValueError('Goal energy adjustment outside supported interval')
    if not 1.0<=protein_g_per_kg<=3.0 or not 0.4<=fat_g_per_kg<=1.6:
        raise ValueError('Review macros per kg')
    increments=training_additions or {'rest':0,'easy':150,'moderate':350,'long':600}
    if set(increments)!=set(LOADS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or -100>v or v>2000 for v in increments.values()):
        raise ValueError('Review per-activity extra energy assumptions')
    resting=10*weight_kg + 6.25*height_cm - 5*age + (5 if sex=='male' else -161)
    baseline=resting*background_multiplier + objective_delta_kcal
    protein=round(weight_kg*protein_g_per_kg,1)
    fat=round(weight_kg*fat_g_per_kg,1)
    targets={}
    for level in LOADS:
        kcal=round((baseline+increments[level])/10)*10
        carbs=round((kcal - protein*4 - fat*9)/4,1)
        if carbs<0:raise ValueError('Chosen energy and protein/fat assumptions leave no carbohydrates')
        targets[level]={'kcal':kcal,'protein_g':protein,'carbs_g':carbs,'fat_g':fat}
    return {'resting_estimate_kcal':round(resting),'background_estimate_kcal':round(resting*background_multiplier),
            'targets':targets,'warning':'Starting estimate only; adjust for actual training, weight trends and professional advice.'}


def inputs_file()->Path:
    return settings.JOURNAL_STATE_DIR/'nutrition_estimation_inputs.json'


def load_inputs(file:Path|None=None)->dict:
    file=Path(file) if file else inputs_file()
    return json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}


def save_inputs(inputs:dict,file:Path|None=None)->Path:
    file=Path(file) if file else inputs_file()
    file.parent.mkdir(parents=True,exist_ok=True)
    tmp=file.with_name(file.name+'.tmp')
    try:
        tmp.write_text(json.dumps(inputs,ensure_ascii=False,indent=2),encoding='utf-8')
        os.chmod(tmp,0o600)
        os.replace(tmp,file)
    finally:tmp.unlink(missing_ok=True)
    return file
