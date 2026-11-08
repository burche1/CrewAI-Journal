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
from src.journal_core.nutrition import week_nutrition

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

first, second = st.tabs(['🍽️ Weekly meals', '🚴 Training timeline'])

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
    shopping=shopping_list(menu,catalog)
    st.dataframe(pd.DataFrame(shopping['items']),hide_index=True,use_container_width=True)
    st.warning(f"{len(shopping['needs_review'])} ingredient entries still need review (alternatives, optional or nonstandard quantities). Raw and cooked weights are never merged.")
    with st.expander('Needs review'):
        st.dataframe(pd.DataFrame(shopping['needs_review']),hide_index=True,use_container_width=True)
    st.download_button('Download shopping list (.md)',as_markdown(shopping),
                       file_name=f'shopping_{start}.md',mime='text/markdown')
    st.download_button('Download consolidated items (.csv)',as_csv(shopping),
                       file_name=f'shopping_{start}.csv',mime='text/csv')
    st.download_button('Download full audit (.json)',json.dumps(shopping,ensure_ascii=False,indent=2),
                       file_name=f'shopping_audit_{start}.json',mime='application/json')
    st.subheader('📊 Nutrition preview')
    nutrition=week_nutrition(menu,catalog)
    data=[]
    for day in nutrition['days']:
        for person in ('person_a','person_b'):
            item=day['persons'][person]
            data.append({'Day':day_labels[day['day_index']],'Person':person,
                        'Known kcal only':item['known_subtotal']['kcal'],
                        'Known protein (g)':item['known_subtotal']['protein_g'],
                        'Known carbs (g)':item['known_subtotal']['carbs_g'],
                        'Known fat (g)':item['known_subtotal']['fat_g'],
                        'Matched ingredients':f"{item['matched_items']}/{item['total_items']}",
                        'Complete':item['complete']})
    st.dataframe(pd.DataFrame(data),hide_index=True,use_container_width=True)
    st.error('Nutrition values above are incomplete illustrative subtotals from generic starter data, NOT complete daily macros. Do not use them for automatic calorie targeting or portion optimization.')
    st.download_button('Download nutrition audit (.json)',json.dumps(nutrition,ensure_ascii=False,indent=2),
                       file_name=f'nutrition_audit_{start}.json',mime='application/json')
