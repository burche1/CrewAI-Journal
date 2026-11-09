"""Local Streamlit week planner. Run: streamlit run planner_app.py --server.address 127.0.0.1"""
from __future__ import annotations
from datetime import date, timedelta
import hashlib
import json
import math

import pandas as pd
import streamlit as st
from src.journal_core.recipe_parser import load_catalog, get_recipe
from src.journal_core.training_parser import load_training
from src.journal_core.weekly import create_menu, monday_start
from src.journal_core.state import (save_menu, approve_menu, load_menu, manage_menu,
                                    list_menu_history, restore_menu_version)
from src.journal_core.schedule import anchor_training, week_for_date, pause_training, resume_training
from src.journal_core.shopping import shopping_list, as_csv, as_markdown
from src.journal_core.nutrition import week_nutrition, reference_file
from src.journal_core.reviews import load_reviews, save_reviews
from src.journal_core.profiles import (MacroTarget, PersonProfile, NutritionProfiles, load_profiles,
                                      save_profiles, LOADS, PERSONS, planned_load,
                                      target_for_person, save_manual_load, load_manual_load)
from src.journal_core.fooddata import search as fdc_search, fetch as fdc_fetch, food_to_row, write_reference, label_to_row
from src.journal_core.optimizer import propose_day
from src.journal_core.targets import estimate_person, load_inputs, save_inputs
from src.journal_core.yields import save_yield, load_yields

st.set_page_config(page_title='CrewAI Journal · Weekly Planner', page_icon='🥗', layout='wide')
st.title('🥗 CrewAI Journal · Weekly Planner')
st.caption('Local planner · original Markdown recipe files stay read-only. Recipe photos load from external websites when enabled; no CrewAI or Google access.')

def catalog_cached():
    return load_catalog()

def training_cached():
    return load_training()

try:
    catalog = catalog_cached()
    training = training_cached()
except (ValueError,OSError) as exc:
    st.error(f'Could not load source files: {exc}')
    st.stop()

first, second, third, fourth = st.tabs(['🍽️ Weekly meals', '🚴 Training timeline', '🎯 Nutrition goals', '🔎 Food reference'])

with second:
    st.subheader('Automatic week progression')
    c1,c2,c3 = st.columns(3)
    with c1:
        start_date=st.date_input('Starting Monday',value=monday_start(date.today())+timedelta(days=7),key='training_anchor_date')
    with c2:
        start_week=st.selectbox('Week at start', ['P1','P2','P3','P4']+[f'W{x}' for x in range(1,53)])
    with c3:
        inspect_date=st.date_input('Preview date',value=date.today())
    if st.button('Save automatic training schedule',type='primary'):
        try:
            anchor_training(start_date,start_week,note='Configured through local web planner')
            st.success('Automatic schedule saved')
        except ValueError as exc:
            st.error(str(exc))
    try:
        state=week_for_date(inspect_date)
        if state:
            st.info(f"Selected week for {inspect_date}: {state['week']} ({state['source']})")
            if state['complete']:
                st.warning('The 56-week plan is complete; please set a new cycle rather than repeating W52 indefinitely.')
            d=training.preview(inspect_date,state['week'])
            st.json(d.model_dump(mode='json'))
        else:
            st.warning('No automatic schedule yet. Choose a start date and save it.')
    except ValueError as exc:
        st.warning(str(exc))
    with st.expander('Pause or resume progression'):
        p1,p2=st.columns(2)
        with p1:
            if st.button('Pause from this week'):
                try:
                    pause_training(date.today(),note='Paused through web planner')
                    st.success('Paused')
                except ValueError as exc:
                    st.error(str(exc))
        with p2:
            resume_date=st.date_input('Resume on Monday',value=monday_start(date.today()),key='resume_date')
            if st.button('Resume on chosen Monday'):
                try:
                    resume_training(resume_date)
                    st.success('Resumed')
                except ValueError as exc:
                    st.error(str(exc))

with fourth:
    st.subheader('Food reference · verified ingredients')
    st.info('This optional database stores calories, protein, carbohydrates and fat per 100 g or ml. '
                   'It is needed for complete nutrition calculations, not for the grocery checklist.')
    st.caption('The old generic demo nutrition CSV is NOT used by default. Add explicitly reviewed USDA foods or verified package labels. No automatic fuzzy matching.')
    ref_path=reference_file()
    st.caption('Local private file: verified_nutrition.csv · '+('available' if ref_path.exists() else 'empty'))
    with st.expander('USDA FoodData Central — search and import',expanded=False):
        st.markdown('An `FDC_API_KEY` in your private `.env` is required. The API is called only when you click Search or Import.')
        query=st.text_input('Search English food name',value='banana raw',key='fdc_query')
        if st.button('Search USDA foods'):
            try: st.session_state['fdc_results']=fdc_search(query)
            except ValueError as exc: st.error(str(exc))
        found=st.session_state.get('fdc_results',[])
        if found: st.dataframe(pd.DataFrame(found),hide_index=True)
        fcol1,fcol2,fcol3=st.columns(3)
        with fcol1: fdc_id=st.number_input('Selected FDC ID',min_value=1,step=1,value=173944)
        with fcol2: mapped_name=st.text_input('Exact recipe ingredient name',value='banana')
        with fcol3: food_state=st.selectbox('Ingredient state',['raw','cooked','drained','as_served'])
        signature=(int(fdc_id),mapped_name.strip(),food_state)
        if st.button('Preview exact USDA food record'):
            try:
                row=food_to_row(fdc_fetch(int(fdc_id)),ingredient=mapped_name,state=food_state)
                st.session_state['fdc_pending']={'signature':signature,'row':row}
            except (ValueError,OSError) as exc:
                st.session_state.pop('fdc_pending',None)
                st.error(str(exc))
        pending=st.session_state.get('fdc_pending')
        if pending and pending['signature']==signature:
            st.json(pending['row'])
            confirmed=st.checkbox('I verified that this exact USDA record matches my ingredient, state and food description')
            if st.button('Save reviewed USDA mapping',disabled=not confirmed):
                try:
                    write_reference(ref_path,pending['row'])
                    st.success(f'Imported {pending["row"]["source"]} for {pending["row"]["ingredient"]}')
                    st.session_state.pop('fdc_pending',None)
                except (ValueError,OSError) as exc:st.error(str(exc))
        else:
            st.caption('Preview the full USDA record, then confirm the specific ingredient match before saving.')
    with st.expander('Verified local product label (e.g. milk per 100 ml)',expanded=False):
        with st.form('label_entry'):
            c1,c2,c3=st.columns(3)
            with c1:
                ingredient=st.text_input('Ingredient, exact recipe name',value='leite')
                label_state=st.selectbox('Measurement state',['as_served','raw','cooked','drained'])
            with c2:
                base_unit=st.selectbox('Label values per 100',['ml','g'])
                label_id=st.text_input('Brand / product / barcode (source)')
            with c3:
                kcal=st.number_input('kcal per 100',min_value=0.,step=1.)
                protein=st.number_input('Protein g per 100',min_value=0.,step=0.1)
                carbs=st.number_input('Carbs g per 100',min_value=0.,step=0.1)
                fat=st.number_input('Fat g per 100',min_value=0.,step=0.1)
            label_ok=st.checkbox('I checked the actual label, not a generic web estimate')
            save_label=st.form_submit_button('Add verified label',disabled=not label_ok)
        if save_label:
            try:
                row=label_to_row(ingredient=ingredient,state=label_state,basis_unit=base_unit,
                                 kcal=kcal,protein_g=protein,carbs_g=carbs,fat_g=fat,label_id=label_id)
                write_reference(ref_path,row)
                st.success('Local label mapping saved. Reference records keep their source.')
            except (ValueError,OSError) as exc: st.error(str(exc))

with third:
    st.subheader('Your nutrition goals · guided starting estimates')
    st.markdown('**What is this?** Training plans indicate which days may need more fuel; '
                'this screen estimates initial energy and protein/carbohydrate/fat targets for each person. '
                '**It does not claim measured energy expenditure or prescribe a medical diet.**')
    st.caption('The starting height/weight/age shown here come from your recipe Markdown notes. '
               'Check current measurements, adjust the activity assumptions, and confirm before saving.')
    existing_profiles=load_profiles()
    remembered=load_inputs()
    values={}
    for person,label,defaults in [
            ('person_a','You',{'weight_kg':80.0,'height_cm':191.0,'age':33,'sex':'male',
                               'background_multiplier':1.35,'objective_delta_kcal':0.0,
                               'protein_g_per_kg':1.6,'fat_g_per_kg':0.8,'use_journal_training':True}),
            ('person_b','Your wife',{'weight_kg':75.0,'height_cm':176.0,'age':33,'sex':'female',
                                    'background_multiplier':1.35,'objective_delta_kcal':0.0,
                                    'protein_g_per_kg':1.6,'fat_g_per_kg':0.8,'use_journal_training':False})]:
        init={**defaults,**remembered.get(person,{})}
        with st.expander(f'👤 {label}: measurements and goals',expanded=True):
            m1,m2,m3,m4=st.columns(4)
            with m1: wt=st.number_input('Weight (kg)',min_value=25.0,max_value=300.0,value=float(init['weight_kg']),step=0.5,key=f'v05_{person}_weight')
            with m2: ht=st.number_input('Height (cm)',min_value=120.0,max_value=230.0,value=float(init['height_cm']),step=1.0,key=f'v05_{person}_height')
            with m3: age=st.number_input('Age',min_value=18,max_value=100,value=int(init['age']),step=1,key=f'v05_{person}_age')
            with m4: sex=st.selectbox('Sex (for resting-energy formula)',['male','female'],index=['male','female'].index(init['sex']),key=f'v05_{person}_sex')
            b1,b2,b3=st.columns(3)
            with b1: mult=st.selectbox('Activity outside scheduled workouts',[1.2,1.3,1.35,1.4,1.5,1.6],index=([1.2,1.3,1.35,1.4,1.5,1.6].index(float(init['background_multiplier'])) if float(init['background_multiplier']) in [1.2,1.3,1.35,1.4,1.5,1.6] else 2),key=f'v05_{person}_background',help='Multiplier for everyday non-training activity; training-day additions below are kept separate.')
            with b2: delta=st.selectbox('Body-weight objective',['maintain','gentle gain','gentle loss'],index={'maintain':0,'gentle gain':1,'gentle loss':2}.get(init.get('objective','maintain'),0),key=f'v05_{person}_objective')
            with b3: use_train=st.checkbox('Use journal training calendar',value=bool(init['use_journal_training']),key=f'v05_{person}_triathlon',help='Turn on only if this person follows the actual CrewAI triathlon training schedule.')
            a,b=st.columns(2)
            with a: ppk=st.slider('Protein (g per kg)',1.0,2.5,float(init['protein_g_per_kg']),step=0.1,key=f'v05_{person}_protein')
            with b: fpk=st.slider('Fat (g per kg)',0.4,1.4,float(init['fat_g_per_kg']),step=0.05,key=f'v05_{person}_fat')
            with st.expander('Advanced: extra energy for training days (editable assumptions)'):
                st.caption('These are editable planning increments, NOT measured calorie burn. Training intensity and duration may differ.')
                adcols=st.columns(3)
                default_add=init.get('training_additions',{'rest':0,'easy':150,'moderate':350,'long':600})
                adds={'rest':0}
                for col,load in zip(adcols,('easy','moderate','long')):
                    with col:
                        adds[load]=st.number_input(f'{load.title()} +kcal',0,2000,int(default_add.get(load,0)),step=50,key=f'v05_{person}_{load}_add')
            objective_adj={'maintain':0.0,'gentle gain':200.0,'gentle loss':-200.0}[delta]
            inputs={'weight_kg':wt,'height_cm':ht,'age':age,'sex':sex,'background_multiplier':mult,
                    'objective_delta_kcal':objective_adj,'objective':delta,
                    'training_additions':adds,'protein_g_per_kg':ppk,'fat_g_per_kg':fpk,
                    'use_journal_training':use_train}
            try:
                calc=estimate_person(**{k:v for k,v in inputs.items() if k not in ('objective','use_journal_training')})
                display=pd.DataFrame([{'Day type':level.title(),'kcal/day':int(t['kcal']),
                                        'Protein g':t['protein_g'],'Carbs g':t['carbs_g'],'Fat g':t['fat_g']}
                                       for level,t in calc['targets'].items()])
                st.dataframe(display,hide_index=True,use_container_width=True)
                st.caption(f"Resting-energy estimate: {calc['resting_estimate_kcal']} kcal; "
                           f"non-training background estimate: {calc['background_estimate_kcal']} kcal. "
                           'Not an exercise calorie tracker.')
                values[person]={'input':inputs,'calc':calc}
            except ValueError as exc:
                st.error(str(exc))
    confirmed=st.checkbox('I have reviewed both estimates and want to use these as provisional meal-planning targets',key='v05_confirm_targets')
    if st.button('💾 Save targets for both people',disabled=not confirmed or len(values)!=2,type='primary'):
        try:
            payload={'people':{},'verified_by_user':True,'notes':'User-reviewed estimates (v0.5), not clinical prescriptions'}
            for person,label in [('person_a','Me'),('person_b','Wife')]:
                payload['people'][person]={'label':label,
                    'use_journal_training':values[person]['input']['use_journal_training'],
                    'targets_by_load':values[person]['calc']['targets']}
            validated=NutritionProfiles.model_validate(payload)
            save_profiles(validated)
            save_inputs({person:values[person]['input'] for person in PERSONS})
            st.success('Reviewed starting targets saved locally. No original recipes have been changed.')
        except (ValueError,OSError) as exc:st.error(str(exc))
    st.divider()
    st.subheader('Individual activity, without copying your triathlon plan')
    st.caption('If someone does not follow the journal training schedule, choose their planned activity for each day. '
               'No exercise completion is inferred.')
    manual_date=st.date_input('Week to classify',value=monday_start(date.today()),key='v05_activity_week')
    manual_week=monday_start(manual_date)
    curr=load_profiles()
    if curr:
        for person in PERSONS:
            if curr.people[person].use_journal_training:
                st.caption(f'{curr.people[person].label}: uses the triathlon calendar; no manual selection needed.')
                continue
            st.markdown(f"**{curr.people[person].label}**")
            columns=st.columns(7)
            for i,col in enumerate(columns):
                d=manual_week+timedelta(days=i)
                old=load_manual_load(person,d)
                with col:
                    load=st.selectbox(d.strftime('%a %d'),['Not set']+list(LOADS),
                                      index=(['Not set']+list(LOADS)).index(old) if old else 0,
                                      key=f'v05_load_{person}_{d.isoformat()}')
                    if load!='Not set' and load!=old:
                        if st.button('Save',key=f'v05_load_save_{person}_{d}'):
                            save_manual_load(person,d,load)
                            st.rerun()
    else:
        st.caption('Save your initial targets first, then classify training for the non-triathlon person.')


with first:
    start=st.date_input('Week starting Monday',value=monday_start(date.today())+timedelta(days=7), key='menu_start')
    if start.weekday()!=0:
        st.error('Choose a Monday as the week start.')
        st.stop()
    saved=load_menu(start.isoformat())
    if saved:
        st.info(f"Existing plan: **{saved.status}**. Approved menus are locked against accidental changes.")
    def clear_week_widgets(week):
        prefix=f'v04_{week}_'
        for key in list(st.session_state.keys()):
            if (str(key).startswith(prefix) or str(key).startswith(f'editor_{week}_')
                    or str(key).startswith(f'factor_a_{week}') or str(key).startswith(f'factor_b_{week}')):
                del st.session_state[key]
    versions=list_menu_history(start.isoformat())
    with st.expander(f'🗂️ Manage this week · {len(versions)} archived versions',expanded=False):
        st.caption('Every revision or reset archives the previous menu and shopping decisions. '
                   'Training history, nutritional targets and other weeks are never altered.')
        if saved:
            x1,x2=st.columns(2)
            with x1:
                revise_ok=st.checkbox('Unlock this week as a draft',key=f'v05_revise_confirm_{start}')
                if st.button('✏️ Revise the selected week',disabled=not revise_ok,key=f'v05_revise_{start}'):
                    try:
                        manage_menu(start.isoformat(),'revise')
                        clear_week_widgets(start)
                        st.rerun()
                    except (ValueError,OSError) as exc:st.error(str(exc))
            with x2:
                reset_ok=st.checkbox('Archive and clear all meal selections for this week',key=f'v05_reset_confirm_{start}')
                if st.button('↩️ Restart this week from scratch',disabled=not reset_ok,key=f'v05_reset_{start}'):
                    try:
                        manage_menu(start.isoformat(),'reset')
                        clear_week_widgets(start)
                        st.rerun()
                    except (ValueError,OSError) as exc:st.error(str(exc))
        if versions:
            previous=st.selectbox('Archived version',versions,format_func=lambda row:
                f"Version {row['version_id']} · {row['prior_status']} · {row['action']} · {row['archived_at'][:19]}",
                key=f'v05_archive_{start}')
            restore_ok=st.checkbox('Restore as a NEW DRAFT (requires re-approval)',key=f'v05_restore_confirm_{start}')
            if st.button('♻️ Restore archived selections',disabled=not restore_ok,key=f'v05_restore_{start}'):
                try:
                    restore_menu_version(start.isoformat(),previous['version_id'])
                    clear_week_widgets(start)
                    st.rerun()
                except (ValueError,OSError) as exc:st.error(str(exc))
    cats=['breakfast','lunch','dinner','snacks']
    names={'breakfast':'Breakfast','lunch':'Lunch','dinner':'Dinner','snacks':'Snacks'}
    show_photos=st.checkbox('Show recipe photos from Markdown (uses external image hosts)',value=True,
                            key='v04_external_recipe_images')
    st.caption('Search by name, browse picture cards and choose exactly seven recipes per category. '
               'The catalog automatically includes recipes you append to the Markdown files.')
    tabs=st.tabs(['🌅 Breakfast','🥙 Lunch','🍲 Dinner','🍌 Snacks'])
    selected={}
    locked=saved is not None and saved.status=='approved'
    for category, tab in zip(cats,tabs):
        with tab:
            state_key=f'v04_{start.isoformat()}_{category}_selected'
            valid_ids={r.id for r in catalog[category]}
            if state_key not in st.session_state:
                st.session_state[state_key]=list(saved.selections.get(category,[])) if saved else []
            # Existing approved selections always remain authoritative.
            if locked:
                st.session_state[state_key]=list(saved.selections[category])
            current_ids=[rid for rid in st.session_state[state_key] if rid in valid_ids]
            st.session_state[state_key]=current_ids
            st.progress(len(current_ids)/7,text=f'{names[category]}: {len(current_ids)} of 7 selected')
            search=st.text_input(f'Search {names[category].lower()} recipes',
                                key=f'v04_search_{category}',placeholder='Name or recipe number')
            recipes=[r for r in catalog[category] if search.casefold().strip() in
                     f'{r.number} {r.title} {r.id}'.casefold()]
            page_count=max(1,math.ceil(len(recipes)/9))
            page=st.selectbox(f'Page ({len(recipes)} matching recipes)',list(range(page_count)),
                              format_func=lambda n:f'{n+1} / {page_count}',
                              key=f'v04_page_{category}')
            page_recipes=recipes[page*9:(page+1)*9]
            if not page_recipes:
                st.info('No matching recipes. Try a different search.')
            columns=st.columns(3)
            for i,r in enumerate(page_recipes):
                with columns[i%3]:
                    with st.container(border=True):
                        if show_photos and r.image_url:
                            try:
                                st.image(r.image_url,use_container_width=True)
                            except (ValueError,OSError):
                                st.caption('Image unavailable; recipe text remains accessible.')
                        st.markdown(f'**{r.number:02d} · {r.title}**')
                        st.caption(f'{r.portions["person_a"][:100]}')
                        is_selected=r.id in current_ids
                        if st.button('✓ Remove' if is_selected else '+ Add recipe',
                                     key=f'v04_card_{start}_{category}_{r.id}',
                                     disabled=locked or (not is_selected and len(current_ids)>=7),
                                     use_container_width=True):
                            if is_selected:
                                st.session_state[state_key]=[x for x in current_ids if x!=r.id]
                            else:
                                st.session_state[state_key]=current_ids+[r.id]
                            st.rerun()
                        with st.expander('Ingredients & preparation'):
                            st.markdown(f'**You:** {r.portions["person_a"]}')
                            st.markdown(f'**Wife:** {r.portions["person_b"]}')
                            if r.preparation: st.caption(r.preparation)
            selected[category]=list(st.session_state[state_key])
            with st.expander(f'Selected for the week ({len(selected[category])}/7)',expanded=False):
                if not selected[category]:
                    st.caption('No recipes selected yet.')
                else:
                    for rid in selected[category]:
                        r=get_recipe(catalog,rid)
                        st.markdown(f'**{r.number:02d} — {r.title}**')
                        st.caption(f'You: {r.portions["person_a"]} | Wife: {r.portions["person_b"]}')
    if not all(len(selected[x])==7 for x in cats):
        st.warning('Choose seven recipes in each of the four tabs to unlock the weekly schedule.')
        st.stop()
    st.subheader('Assign your selected recipes to weekdays')
    st.caption('Use the dropdown in each cell to rearrange the recipes. Each selected recipe must appear once per category.')
    display_names={}
    labels={}
    for category in cats:
        labels[category]={r.id: f'{r.number:02d} · {r.title}' for r in catalog[category]}
        display_names[category]={v:k for k,v in labels[category].items()}
    day_labels=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    rows=[]
    for index,weekday in enumerate(day_labels):
        row={'Day':f'{weekday} · {(start+timedelta(days=index)).isoformat()}'}
        for category in cats:
            row[names[category]]=labels[category][selected[category][index]]
        rows.append(row)
    edited=st.data_editor(pd.DataFrame(rows),hide_index=True, num_rows='fixed',
        disabled=True if locked else ['Day'],
        key=f'editor_{start}_{hashlib.sha1(json.dumps(selected,sort_keys=True).encode()).hexdigest()[:12]}',
        column_config={names[cat]: st.column_config.SelectboxColumn(names[cat],options=[labels[cat][rid] for rid in selected[cat]],required=True)
                       for cat in cats})
    choices={}
    errors=[]
    for category in cats:
        try:
            chosen=[display_names[category][x] for x in edited[names[category]].tolist()]
        except KeyError:
            errors.append(f'Invalid selection in {names[category]}.')
            continue
        if len(chosen)!=7 or len(set(chosen))!=7:
            errors.append(f'{names[category]}: each of the seven chosen recipes must appear exactly once.')
        choices[category]=chosen
    st.subheader('Portions for the two people')
    st.caption('Manual portion factors only. These do NOT imply proven energy/macro targets or automatic training-based optimization.')
    base=saved.portion_factors if saved else {'person_a':1.0,'person_b':1.0}
    f1,f2=st.columns(2)
    with f1:
        fa=st.slider('Person A (you)',0.50,1.50,float(base.get('person_a',1.0)),0.05,key=f'factor_a_{start}',disabled=saved is not None and saved.status=='approved')
    with f2:
        fb=st.slider('Person B (wife)',0.50,1.50,float(base.get('person_b',1.0)),0.05,key=f'factor_b_{start}',disabled=saved is not None and saved.status=='approved')
    if errors:
        for err in errors: st.error(err)
        st.stop()
    menu=create_menu(start,catalog,choices)
    menu.portion_factors={'person_a':fa,'person_b':fb}
    status=saved.status if saved else 'new'
    b1,b2=st.columns(2)
    with b1:
        if st.button('💾 Save as draft',disabled=status=='approved',type='primary'):
            try:
                save_menu(menu)
                st.success('Draft saved locally. Review and approve when ready.')
            except ValueError as exc: st.error(str(exc))
    with b2:
        if st.button('✅ Approve saved draft',disabled=status=='approved'):
            current=load_menu(start.isoformat())
            if not current:
                st.error('Save draft first.')
            elif current.selections != choices or current.portion_factors != menu.portion_factors:
                st.error('The editor has unsaved changes. Save the draft before approval.')
            elif any(catalog[c][0].source_sha256 != current.source_hashes.get(c) for c in cats):
                st.error('A source Markdown file changed. Reload and review before approval.')
            else:
                approve_menu(start.isoformat())
                st.success('Approved plan locked! Daily journal may now read it.')
    st.subheader('🛒 Einkaufsliste — organized for German supermarkets')
    shopping=shopping_list(menu,catalog,resolutions=load_reviews(menu.week_start))
    market=shopping['supermarket']
    unresolved=shopping['review_groups']
    st.caption('Consolidated for two people. Products are grouped by supermarket aisle; '
               'raw/cooked values remain separate until a conversion is verified.')
    k1,k2,k3=st.columns(3)
    k1.metric('Distinct products',len(market))
    k2.metric('Choices to review',len(unresolved))
    k3.metric('Cooked/raw checks',shopping['conversion_count'])
    if unresolved:
        st.warning(f'{len(unresolved)} ingredient decisions still need your attention. '
                   'You can resolve matching occurrences together below.')
    elif shopping['conversion_count']:
        st.info('Ingredient choices resolved. Some products still need raw/cooked '
                'purchase-weight conversion; no quantities were invented.')
    else:
        st.success('No unresolved ingredients or raw/cooked conflicts remain.')

    # Only show market-facing rows, not technical person/hash/audit fields.
    from src.journal_core.grocery import SECTIONS
    for section in SECTIONS:
        aisle=[item for item in market if item['section']==section]
        if not aisle:
            continue
        with st.expander(f'{section} · {len(aisle)} products',expanded=True):
            view=pd.DataFrame([{'Product':x['label'],'To buy':x['quantity_display'],
                                'Attention':x['note']} for x in aisle])
            st.dataframe(view,hide_index=True,use_container_width=True)

    with st.expander(f'🧩 Resolve ingredients · {len(unresolved)} groups',expanded=bool(unresolved)):
        st.caption('Types are separated: substitute an alternative, split a mixture, include/skip optional items, '
                   'or specify quantities for an incomplete recipe. One saved choice applies to both people and matching days.')
        if unresolved:
            type_labels={'mixed_ingredients':'🥕 Mixed ingredients — decide percentages',
                         'alternative':'🔁 Alternative — choose a product',
                         'optional':'☑ Optional — include or skip',
                         'prepared_dish':'🍲 Prepared dish — review recipe components',
                         'missing_quantity':'⚖️ Missing quantity',
                         'ingredient_choice':'🔍 Product/quantity choice',
                         'fruit_choice':'🍎 Choose the fruit'}
            grouped={kind:[g for g in unresolved if g['kind']==kind]
                     for kind in type_labels}
            for kind,members in grouped.items():
                if members:
                    st.caption(f'{type_labels[kind]}: {len(members)}')
            ids={g['group_id']:g for g in unresolved}
            group_id=st.selectbox('Ingredient needing attention',list(ids),
                format_func=lambda gid:f"{type_labels.get(ids[gid]['kind'],'Review')} · {ids[gid]['ingredient']} ({ids[gid]['count']} uses)",
                key=f'v05_review_group_{start}')
            group=ids[group_id]
            st.markdown(f"**Source description:** {group['ingredient']}")
            st.caption(f"Seen in {group['recipes']}. Original per-person portions remain unchanged.")
            action_labels={
                'mixed_ingredients':['Split by percentages','Use one ingredient instead','Specify a complete replacement','Skip (already stocked)'],
                'alternative':['Choose one ingredient','Split by percentages','Specify a complete replacement','Skip (already stocked)'],
                'optional':['Skip (not needed)','Choose to include','Specify a complete replacement'],
                'prepared_dish':['Specify a complete replacement','Skip (already stocked)'],
                'missing_quantity':['Specify a complete replacement','Skip (already stocked)'],
                'ingredient_choice':['Choose one ingredient','Specify a complete replacement','Skip (already stocked)'],
                'fruit_choice':['Choose one ingredient','Specify a complete replacement'],
            }
            action_options=action_labels.get(group['kind'],action_labels['ingredient_choice'])
            if not group['can_choose']:
                action_options=[a for a in action_options if a not in ('Choose one ingredient','Split by percentages','Choose to include','Use one ingredient instead')]
            action=st.radio('What does this recipe mean?',action_options,
                key=f'v05_review_action_{start}_{group_id}',horizontal=True)
            resolution=None
            if action=='Split by percentages':
                parts=group['choices']
                if len(parts)<2 or len(parts)>6:
                    st.warning('Please specify component ingredients and amounts using a complete replacement.')
                else:
                    st.caption('Enter how to distribute the source quantity. The total MUST equal 100% (not guessed).')
                    cols=st.columns(len(parts))
                    values=[]
                    for i,(col,name) in enumerate(zip(cols,parts)):
                        with col:
                            share=st.number_input(f'{name} (%)',min_value=0.0,max_value=100.0,
                                value=round(100/len(parts),2) if i<len(parts)-1 else round(100-round(100/len(parts),2)*(len(parts)-1),2),
                                step=5.0,key=f'v05_part_{group_id}_{i}')
                            values.append({'name':name,'percent':share})
                    total_share=sum(p['percent'] for p in values)
                    if abs(total_share-100)>0.001:st.warning(f'Total: {total_share:g}% · adjust to exactly 100%.')
                    resolution={'action':'split','parts':values}
            elif action in ('Choose one ingredient','Choose to include','Use one ingredient instead'):
                choices=group['choices'] or ['fruta','banana','maca','laranja']
                selected_name=st.selectbox('Product to buy',choices,key=f'v05_choice_{start}_{group_id}')
                other_name=st.text_input('Or type a different exact product (optional)',
                                         key=f'v05_other_{start}_{group_id}')
                resolution={'action':'choose','name':other_name or selected_name}
            elif action=='Specify a complete replacement':
                cc1,cc2,cc3=st.columns(3)
                with cc1: name=st.text_input('Product',key=f'v05_name_{start}_{group_id}')
                with cc2: qty=st.number_input('Quantity for EACH source occurrence',min_value=0.0,step=1.0,key=f'v05_qty_{start}_{group_id}')
                with cc3: unit=st.selectbox('Unit',['g','kg','ml','l','un'],key=f'v05_unit_{start}_{group_id}')
                state=st.selectbox('Ingredient state',['as_served','raw','cooked','drained'],key=f'v05_state_{start}_{group_id}')
                st.caption('This quantity is per occurrence BEFORE individual portion scaling. '
                           'For a homemade prepared meal, list its actual components separately in the source recipe for accurate nutrition.')
                resolution={'action':'replace','name':name,'quantity':qty,'unit':unit,'state':state}
            else:resolution={'action':'skip'}
            if st.button('✓ Apply this choice to all matching recipes',type='primary',key=f'v05_apply_{start}_{group_id}'):
                try:
                    decisions=load_reviews(menu.week_start)
                    decisions[group_id]=resolution
                    save_reviews(menu.week_start,decisions)
                    st.rerun()
                except (ValueError,OSError,TypeError) as exc:st.error(str(exc))
        else:st.success('No ingredient choices remain unresolved.')
        with st.expander('Manage saved ingredient decisions'):
            stored=load_reviews(menu.week_start)
            st.caption(f'{len(stored)} saved decisions for this week.')
            if stored:
                chosen=st.selectbox('Remove a saved decision',list(stored),
                                    format_func=lambda gid:f'{gid}: {stored[gid]["action"]}',key=f'v05_review_remove_{start}')
                if st.button('Remove selected decision',key=f'v05_review_rm_{start}'):
                    del stored[chosen]
                    save_reviews(menu.week_start,stored)
                    st.rerun()
    if shopping['conversion_needed']:
        with st.expander(f'⚖️ Convert cooked/drained weights to raw purchases ({len(shopping["conversion_needed"])} products)',expanded=True):
            st.caption('Use a measured batch or a published food-specific yield. '
                       'The app applies it to every matching ingredient after you confirm it; '
                       'no generic conversion is assumed. Cooked yield can be greater or smaller than raw weight.')
            conversion_rows=shopping['conversion_needed']
            names={row['ingredient']:row for row in conversion_rows}
            selected_food=st.selectbox('Product',list(names),format_func=lambda n:names[n]['label'],key=f'v05_yield_food_{start}')
            selected_row=names[selected_food]
            pending_states=[x.split('(')[-1].rstrip(')') for x in selected_row['pending_states']]
            selected_state=st.selectbox('Prepared state to convert',sorted(set(pending_states)),key=f'v05_yield_state_{start}')
            st.info(f'Current breakdown: {selected_row["quantity_display"]}')
            if selected_row['unit']!='g' or selected_state=='unknown':
                st.warning('This entry cannot yet be converted reliably. The source needs a known food preparation state and gram-based quantities. Review the original recipe first.')
            with st.form(f'v05_yield_{start}_{selected_food}_{selected_state}'):
                yc1,yc2=st.columns(2)
                with yc1: raw_g=st.number_input('Raw purchase weight (g)',min_value=1.0,value=100.0,step=10.0)
                with yc2: prepared_g=st.number_input(f'{selected_state.title()} usable weight (g)',min_value=1.0,value=250.0,step=10.0)
                method=st.text_input('Preparation method',placeholder='e.g. simmered in water, measured after draining')
                source=st.text_input('Evidence / source',placeholder='e.g. weighed at home 2026-11-08, or exact USDA table reference')
                acknowledge=st.checkbox('These weights describe the same food and preparation method')
                submit=st.form_submit_button('Save this yield and automatically recalculate purchases',
                                             disabled=not acknowledge or selected_row['unit']!='g' or selected_state=='unknown')
            if submit:
                try:
                    saved_yield=save_yield({'product':selected_food,'from_state':selected_state,
                        'raw_grams':raw_g,'prepared_grams':prepared_g,'method':method,'source':source})
                    st.success(f"Saved reviewed yield: {saved_yield['factor']:.3f} g {selected_state} per g raw")
                    st.rerun()
                except (ValueError,OSError) as exc:st.error(str(exc))
    else:
        st.caption('No unresolved cooking/purchase weight conversions.')
    download_md,download_csv=st.columns(2)
    with download_md:
        st.download_button('📋 Download supermarket checklist (.md)',as_markdown(shopping),
                           file_name=f'shopping_{start}.md',mime='text/markdown',
                           use_container_width=True)
    with download_csv:
        st.download_button('📑 Download aisle-organized list (.csv)',as_csv(shopping),
                           file_name=f'shopping_{start}.csv',mime='text/csv',
                           use_container_width=True)
    with st.expander('Advanced: shopping audit data (for debugging only)',expanded=False):
        st.download_button('Download full shopping audit (.json)',
                           json.dumps(shopping,ensure_ascii=False,indent=2),
                           file_name=f'shopping_audit_{start}.json',mime='application/json')
    st.subheader('📊 Verified nutrition preview')
    try:
        nutrition=week_nutrition(menu,catalog)
    except (OSError,ValueError) as exc:
        nutrition=None
        st.info(f'No verified nutrition reference yet: {exc}. Add USDA foods or labels in Food reference.')
    if nutrition is not None:
        data=[]
        for day in nutrition['days']:
            for person in ('person_a','person_b'):
                item=day['persons'][person]
                data.append({'Day':day_labels[day['day_index']],'Person':person,
                             'Known kcal':item['known_subtotal']['kcal'],
                             'Protein g':item['known_subtotal']['protein_g'],
                             'Carbs g':item['known_subtotal']['carbs_g'],
                             'Fat g':item['known_subtotal']['fat_g'],
                             'Coverage':f"{item['matched_items']}/{item['total_items']}",
                             'Complete':item['complete']})
        st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True)
        st.warning('Only matched food data is counted. Missing values are NOT zero. Never optimize on incomplete days.')
        st.download_button('Download nutrition audit (.json)',json.dumps(nutrition,ensure_ascii=False,indent=2),
                           file_name=f'nutrition_audit_{start}.json',mime='application/json')
        profiles=load_profiles()
        if profiles and profiles.verified_by_user:
            st.subheader('Training-aware portion proposal (read-only)')
            dcol,pcol=st.columns(2)
            with dcol: day_selected=st.selectbox('Day',list(range(7)),format_func=lambda i:day_labels[i])
            with pcol: person_selected=st.selectbox('Person',list(PERSONS),format_func=lambda p:profiles.people[p].label)
            current_date=start+timedelta(days=day_selected)
            try:
                status=target_for_person(profiles,person_selected,current_date)
                if status['status']=='ready':
                    from src.journal_core.profiles import MacroTarget
                    suggestion=propose_day(menu,catalog,day_selected,person_selected,MacroTarget(**status['target']))
                    st.json({'activity':status,'proposal':suggestion})
                    if suggestion['status']=='blocked':
                        st.info('The optimizer is blocked until all chosen ingredients have verified nutritional coverage.')
                else:
                    st.warning('Choose this person’s activity classification in Nutrition goals first.')
            except (OSError,ValueError) as exc:st.warning(str(exc))
