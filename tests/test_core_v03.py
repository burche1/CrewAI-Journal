"""v0.3 source verification and conservative optimization tests; no network."""
from datetime import date
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import csv
import unittest

from src.journal_core.fooddata import food_to_row,write_reference,label_to_row
from src.journal_core.profiles import (MacroTarget, PersonProfile, NutritionProfiles,
                                      save_profiles,load_profiles,planned_load, target_for_person, save_manual_load)
from src.journal_core.reviews import review_id,save_reviews,load_reviews,validate_resolution
from src.journal_core.recipe_parser import load_catalog
from src.journal_core.weekly import create_menu
from src.journal_core.shopping import shopping_list
from src.journal_core.nutrition import load_reference,reference_file
from src.journal_core.optimizer import propose_day
from src.journal_core.schedule import anchor_training

FOOD={'fdcId':173944,'description':'Bananas, raw','dataType':'SR Legacy','foodNutrients':[
    {'nutrient':{'id':1003,'unitName':'g'},'amount':1.1},
    {'nutrient':{'id':1004,'unitName':'g'},'amount':0.3},
    {'nutrient':{'id':1005,'unitName':'g'},'amount':23.0},
    {'nutrient':{'id':1008,'unitName':'kcal'},'amount':89.0},
]}

class CoreV03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog()
        cls.menu=create_menu(date(2026,11,9), cls.catalog,
                        {category:[r.id for r in recipes[:7]] for category,recipes in cls.catalog.items()})

    def test_search_posts_official_filter_without_external_calls(self):
        from io import BytesIO
        from src.journal_core.fooddata import search
        import json
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return self.payload
            payload=json.dumps({'foods':[{'fdcId':173944,'description':'Bananas raw',
                          'dataType':'SR Legacy'}]}).encode()
        with patch('src.journal_core.fooddata.urlopen',return_value=FakeResponse()) as request:
            rows=search('banana',api_key='test_fake_key')
            self.assertEqual(rows[0]['fdc_id'],173944)
            obj=request.call_args.args[0]
            self.assertEqual(obj.get_method(),'POST')
            self.assertIn('Foundation',obj.data.decode())

    def test_fdc_mapping_and_source(self):
        row=food_to_row(FOOD,ingredient='banana',state='as_served')
        self.assertIn('173944',row['source'])
        self.assertEqual(row['basis_unit'],'g')
        with self.assertRaises(ValueError):
            food_to_row({**FOOD,'dataType':'Branded'},ingredient='banana',state='raw')
        with self.assertRaises(ValueError):
            food_to_row({**FOOD,'foodNutrients':FOOD['foodNutrients'][:2]},ingredient='banana',state='raw')

    def test_verification_storage_private_and_duplicate_protection(self):
        row=food_to_row(FOOD,ingredient='banana',state='as_served')
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)/'verified.csv'
            write_reference(dest,row)
            self.assertEqual(len(load_reference(dest)),1)
            with self.assertRaises(ValueError):write_reference(dest,row)
            write_reference(dest,row,replace=True)
            milk=label_to_row(ingredient='leite',state='as_served',basis_unit='ml',
                              kcal=61.,protein_g=3.2,carbs_g=4.8,fat_g=3.3,label_id='Example brand test carton')
            write_reference(dest,milk)
            self.assertEqual(len(load_reference(dest)),2)
            self.assertTrue(milk['source'].startswith('LABEL:'))

    def test_profiles_reject_missing_or_inconsistent(self):
        with self.assertRaises(ValueError):
            MacroTarget(kcal=4000,protein_g=10,carbs_g=10,fat_g=10)
        target=MacroTarget(kcal=2000,protein_g=100,carbs_g=250,fat_g=67)
        profiles=NutritionProfiles(verified_by_user=True,
          people={person:PersonProfile(label=person,targets_by_load={day:target for day in ('rest','easy','moderate','long')})
                  for person in ('person_a','person_b')})
        with TemporaryDirectory() as tmp:
            location=Path(tmp)/'profiles.json'
            save_profiles(profiles,location)
            self.assertEqual(load_profiles(location).people['person_a'].label,'person_a')

    def test_shopping_review_and_aggregation(self):
        initial=shopping_list(self.menu,self.catalog)
        self.assertTrue(initial['needs_review'])
        row=initial['needs_review'][0]
        with TemporaryDirectory() as tmp:
            with patch('src.journal_core.reviews.settings.JOURNAL_STATE_DIR',Path(tmp)):
                resolution={row['review_id']:{'action':'skip'}}
                save_reviews(self.menu.week_start,resolution)
                self.assertEqual(load_reviews(self.menu.week_start),resolution)
                revised=shopping_list(self.menu,self.catalog,resolutions=load_reviews(self.menu.week_start))
                self.assertEqual(len(revised['needs_review']),len(initial['needs_review'])-1)
                self.assertEqual(revised['reviewed'],1)
        with self.assertRaises(ValueError):validate_resolution({'action':'replace','name':'tomate','quantity':0,'unit':'g','state':'raw'})

    def test_optimizer_blocks_unverified_and_partial(self):
        target=MacroTarget(kcal=2000,protein_g=100,carbs_g=250,fat_g=67)
        demo={'banana','as_served'}
        self.assertEqual(propose_day(self.menu,self.catalog,0,'person_a',target,
                  reference={('banana','as_served'):{'source':'demo','basis_unit':'g','kcal':89,'protein_g':1,'carbs_g':23,'fat_g':0.3}})['status'],'blocked')
        self.assertEqual(propose_day(self.menu,self.catalog,0,'person_a',target,
                  reference={('banana','as_served'):{'source':'USDA_FDC:1','basis_unit':'g','kcal':89,'protein_g':1,'carbs_g':23,'fat_g':0.3}})['status'],'blocked')

    def test_optimizer_with_complete_reviewed_reference_is_advisory(self):
        from src.journal_core.models import Recipe, Ingredient
        from src.journal_core.optimizer import propose_day
        ref={('aveia','as_served'):{'source':'USDA_FDC:100', 'basis_unit':'g',
                'kcal':370.,'protein_g':13.,'carbs_g':65.,'fat_g':7.},
             ('leite','as_served'):{'source':'LABEL:reviewed test carton','basis_unit':'ml',
                'kcal':60.,'protein_g':3.,'carbs_g':5.,'fat_g':3.}}
        cats={}
        selections={}
        for category in ('breakfast','lunch','dinner','snacks'):
            rid=f'{category}:01'
            ing=Ingredient(raw='100 g aveia',name='aveia',quantity=100,unit='g',measurement_state='as_served')
            cats[category]=[Recipe(id=rid,category=category,number=1,title='test',source_file='test',
                source_sha256='0'*64,source_start_line=1,source_end_line=2,
                portions={'person_a':'100 g aveia','person_b':'100 g aveia'},
                ingredients={'person_a':[ing],'person_b':[ing]},markdown='test')]
            selections[category]=[rid]*7
        menu=SimpleNamespace(selections=selections)
        target=MacroTarget(kcal=1500,protein_g=55,carbs_g=240,fat_g=36)
        proposal=propose_day(menu,cats,0,'person_a',target,reference=ref)
        self.assertEqual(proposal['status'],'suggestion_only')
        self.assertEqual(len(proposal['meal_multipliers_relative_to_approved_portions']),4)
        self.assertTrue(all(0.85<=v<=1.15 for v in proposal['meal_multipliers_relative_to_approved_portions'].values()))

    def test_wife_activity_is_not_copied_from_triathlon(self):
        target=MacroTarget(kcal=2000,protein_g=100,carbs_g=250,fat_g=67)
        profiles=NutritionProfiles(verified_by_user=True,people={
          'person_a':PersonProfile(label='Me',use_journal_training=True,
                targets_by_load={day:target for day in ('rest','easy','moderate','long')}),
          'person_b':PersonProfile(label='Wife',use_journal_training=False,
                targets_by_load={day:target for day in ('rest','easy','moderate','long')})})
        d=date(2026,11,14)
        with TemporaryDirectory() as tmp:
            from src.journal_core import profiles as pf
            with patch.object(pf.settings,'JOURNAL_STATE_DIR',Path(tmp)):
                self.assertEqual(target_for_person(profiles,'person_b',d)['status'],'needs_activity')
                save_manual_load('person_b',d,'rest')
                self.assertEqual(target_for_person(profiles,'person_b',d)['load'],'rest')

    def test_prep_week_load_is_easy_and_calendar_anchor(self):
        with TemporaryDirectory() as tmp:
            with patch('src.journal_core.state.database_path',return_value=Path(tmp)/'state.db'):
                anchor_training(date(2026,11,9),'P1')
                self.assertEqual(planned_load(date(2026,11,14))['load'],'easy')
                self.assertEqual(planned_load(date(2026,11,9))['load'],'rest')
                self.assertEqual(planned_load(date(2026,12,12))['load'],'long')

if __name__=='__main__':unittest.main()
