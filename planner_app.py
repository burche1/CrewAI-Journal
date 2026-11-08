"""Local Streamlit week planner. Run: streamlit run planner_app.py --server.address 127.0.0.1"""
from __future__ import annotations
from datetime import date, timedelta
import json

import pandas as pd
import streamlit as st
from src.journal_core.recipe_parser import load_catalog, get_recipe
from src.journal_core.training_parser import load_training
from src.journal_core.weekly import create_menu, monday_start
from src.journal_core.state import save_menu, approve_menu, load_menu
from src.journal_core.schedule import anchor_training, week_for_date, pause_training, resume_training
from src.journal_core.shopping import shopping_list, as_csv, as_markdown
from src.journal_core.nutrition import week_nutrition, reference_file
from src.journal_core.reviews import load_reviews, save_reviews
from src.journal_core.profiles import (MacroTarget, PersonProfile, NutritionProfiles, load_profiles,
                                      save_profiles, LOADS, PERSONS, planned_load,
                                      target_for_person, save_manual_load, load_manual_load)
from src.journal_core.fooddata import search as fdc_search, fetch as fdc_fetch, food_to_row, write_reference, label_to_row
from src.journal_core.optimizer import propose_day

st.set_page_config(page_title='CrewAI Journal · Weekly Planner', page_icon='🥗', layout='wide')
st.title('🥗 CrewAI Journal · Weekly Planner')
st.caption('Local, offline, read-only recipe sources. No CrewAI or Google access.')

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

first, second, third = st.tabs(['🍽️ Weekly meals', '🚴 Training timeline', '🥗 Nutrition setup'])

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

with third:
    st.subheader('Verified food data')
    st.caption('The old generic demo nutrition CSV is NOT used by default. Add explicitly reviewed USDA foods or verified package labels. No automatic fuzzy matching.')
    ref_path=reference_file()
    st.info(f'Local private reference: {ref_path} · {"exists" if ref_path.exists() else "not created yet"}')
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
    st.divider()
    st.subheader('Individual nutrition targets — manually confirmed')
    st.caption('You and your wife have separate targets. This interface does not calculate medical calorie requirements. Enter reviewed values for rest/easy/moderate/long days.')
    current=load_profiles()
    with st.form('profile_form'):
        profiles_data={}
        for person,default_label in [('person_a','Me'),('person_b','Wife')]:
            st.markdown(f'**{default_label}**')
            existing=current.people[person] if current else None
            label=st.text_input('Label',value=existing.label if existing else default_label,key=f'{person}_label')
            use_training=st.checkbox('Use my CrewAI triathlon calendar for activity classification',
                value=existing.use_journal_training if existing else person=='person_a',
                key=f'{person}_use_journal')
            targets={}
            for load in LOADS:
                st.caption(f'{load.title()} training load')
                values=existing.targets_by_load[load] if existing else None
                cols=st.columns(4)
                for idx,(field,caption) in enumerate([('kcal','kcal/day'),('protein_g','Protein g/day'),
                                                      ('carbs_g','Carbs g/day'),('fat_g','Fat g/day')]):
                    with cols[idx]:
                        targets.setdefault(load,{})[field]=st.number_input(
                            f'{load} {caption}',min_value=0.0,max_value=10000.0,step=5.0,
                            value=float(getattr(values,field)) if values else 0.0,key=f'{person}_{load}_{field}')
            profiles_data[person]={'label':label,'use_journal_training':use_training,'targets_by_load':targets}
        agree=st.checkbox('I reviewed both people’s numbers and agree to use these as planning targets',
                          value=current.verified_by_user if current else False)
        save_target=st.form_submit_button('Save nutrition targets')
    if save_target:
        try:
            if not agree:raise ValueError('You must confirm the individual targets before saving.')
            profile=NutritionProfiles(people=profiles_data,verified_by_user=True)
            save_profiles(profile)
            st.success('Private nutrition profiles saved locally (excluded from Git).')
        except ValueError as exc:st.error(str(exc))
    st.caption('For training load, P1–P4 stays easy even on weekends. The main cycle treats long weekend sessions as long days. Actual session changes require review.')
    if current and current.verified_by_user:
        inspect=st.date_input('Preview training-derived target date',value=date.today(),key='nutrition_target_date')
        try:
            statuses={x:target_for_person(current,x,inspect) for x in PERSONS}
            for person in PERSONS:
                if statuses[person]['status']=='needs_activity':
                    st.warning(f'{current.people[person].label}: no activity selection for this day')
                    activity=st.selectbox(f'Activity for {current.people[person].label}',LOADS,
                                          key=f'manual_load_{person}_{inspect.isoformat()}')
                    if st.button(f'Save activity for {current.people[person].label}',key=f'save_activity_{person}_{inspect}'):
                        save_manual_load(person,inspect,activity)
                        st.success('Activity saved locally; reload to update targets')
            st.json(statuses)
        except (OSError,ValueError) as exc:st.warning(str(exc))

with first:
    start=st.date_input('Week starting Monday',value=monday_start(date.today())+timedelta(days=7), key='menu_start')
    if start.weekday()!=0:
        st.error('Choose a Monday as the week start.')
        st.stop()
    saved=load_menu(start.isoformat())
    if saved:
        st.info(f"Existing plan: **{saved.status}**. Approved menus are locked against accidental changes.")
    cats=['breakfast','lunch','dinner','snacks']
    names={'breakfast':'Breakfast','lunch':'Lunch','dinner':'Dinner','snacks':'Snacks'}
    tabs=st.tabs(['🌅 Breakfast','🥙 Lunch','🍲 Dinner','🍌 Snacks'])
    selected={}
    for category, tab in zip(cats,tabs):
        with tab:
            options=[r.id for r in catalog[category]]
            id_to_title={r.id:f'{r.number:02d} — {r.title}' for r in catalog[category]}
            defaults=saved.selections[category] if saved else []
            selected[category]=st.multiselect(
                f'Select exactly seven {names[category].lower()} recipes',
                options, default=defaults, format_func=lambda rid,m=id_to_title:m[rid],
                max_selections=7, key=f'{start}_{category}_recipes', disabled=saved is not None and saved.status=='approved')
            st.caption(f'{len(selected[category])}/7 chosen · click items to choose, search by recipe title')
            with st.expander('See details of selected recipes'):
                for rid in selected[category]:
                    r=get_recipe(catalog,rid)
                    st.markdown(f'**{r.title}** · {rid}')
                    st.markdown(f'**You:** {r.portions["person_a"]}')
                    st.markdown(f'**Wife:** {r.portions["person_b"]}')
                    if r.preparation:
                        st.caption(r.preparation)
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
        disabled=True if saved is not None and saved.status=='approved' else ['Day'],key=f'editor_{start}',
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
    st.subheader('🛒 Shopping list preview')
    shopping=shopping_list(menu,catalog,resolutions=load_reviews(menu.week_start))
    st.dataframe(pd.DataFrame(shopping['items']),hide_index=True,use_container_width=True)
    st.warning(f"{len(shopping['needs_review'])} unresolved ingredient entries · {shopping['reviewed']} reviewed. Cooked/raw weights still require purchase-state checking.") if shopping['needs_review'] else st.success('All ambiguous entries reviewed. Verify raw/cooked conversions before purchasing.')
    with st.expander('Needs review'):
        st.dataframe(pd.DataFrame(shopping['needs_review']),hide_index=True,use_container_width=True)
    with st.expander('Resolve shopping list ingredients',expanded=False):
        st.caption('Choose skip (e.g. optional ingredient) or replace with one exact ingredient, quantity and preparation state. Saved corrections are separate from your approved weekly menu.')
        pending=shopping['needs_review']
        if pending:
            data=[{'ID':x['review_id'],'Recipe':x['recipe'],'Original':x['ingredient'],
                   'Action':'pending','Name':'','Quantity':0.0,'Unit':'g','State':'as_served'} for x in pending]
            reviewed_table=st.data_editor(pd.DataFrame(data),hide_index=True,num_rows='fixed',
                disabled=['ID','Recipe','Original'],key=f'shopping_review_{start}',
                column_config={'Action':st.column_config.SelectboxColumn('Action',options=['pending','skip','replace']),
                               'Unit':st.column_config.SelectboxColumn('Unit',options=['g','kg','ml','l','un']),
                               'State':st.column_config.SelectboxColumn('State',options=['raw','cooked','drained','as_served'])})
            if st.button('Save shopping resolutions',key=f'save_review_{start}'):
                try:
                    decisions=load_reviews(menu.week_start)
                    for _,entry in reviewed_table.iterrows():
                        action=entry['Action']
                        if action=='pending':continue
                        decisions[entry['ID']]={'action':action} if action=='skip' else {
                            'action':'replace','name':str(entry['Name']),
                            'quantity':float(entry['Quantity']),'unit':str(entry['Unit']),'state':str(entry['State'])}
                    save_reviews(menu.week_start,decisions)
                    st.success('Saved. Reload the page to recalculate the shopping list.')
                except (ValueError,OSError,TypeError) as exc:st.error(str(exc))
        if st.button('Reset ALL shopping resolutions for this week',key=f'reset_review_{start}'):
            save_reviews(menu.week_start,{})
            st.info('Review decisions cleared; reload to review unresolved entries again.')
    st.download_button('Download shopping list (.md)',as_markdown(shopping),
                       file_name=f'shopping_{start}.md',mime='text/markdown')
    st.download_button('Download consolidated items (.csv)',as_csv(shopping),
                       file_name=f'shopping_{start}.csv',mime='text/csv')
    st.download_button('Download full audit (.json)',json.dumps(shopping,ensure_ascii=False,indent=2),
                       file_name=f'shopping_audit_{start}.json',mime='application/json')
    st.subheader('📊 Verified nutrition preview')
    try:
        nutrition=week_nutrition(menu,catalog)
    except (OSError,ValueError) as exc:
        nutrition=None
        st.info(f'No verified nutrition reference yet: {exc}. Add USDA foods or labels in Nutrition setup.')
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
                    st.warning('Choose this person’s activity classification in Nutrition setup first.')
            except (OSError,ValueError) as exc:st.warning(str(exc))
