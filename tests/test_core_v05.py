"""v0.5 regression: archived plan revisions, measured yields, split decisions, reviewed targets."""
from __future__ import annotations
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sqlite3
import ast
import settings
from src.journal_core.recipe_parser import load_catalog
from src.journal_core.weekly import create_menu
from src.journal_core import state
from src.journal_core.reviews import save_reviews, load_reviews, group_review_id, validate_resolution
from src.journal_core.shopping import shopping_list
from src.journal_core.grocery import supermarket_rows
from src.journal_core.yields import validate_yield, save_yield, load_yields, purchase_raw
from src.journal_core.targets import estimate_person, save_inputs, load_inputs

class NewFlowTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog()
        cls.menu=create_menu(date(2026,11,9),cls.catalog,
            {cat:[r.id for r in recipes[:7]] for cat,recipes in cls.catalog.items()})

    def test_reset_archives_approved_and_review_records_and_can_restore(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/'state.sqlite3'
            with patch.object(state,'database_path',return_value=db),patch.object(settings,'JOURNAL_STATE_DIR',Path(tmp)):
                state.save_menu(self.menu)
                state.approve_menu(self.menu.week_start)
                gid=group_review_id('100 g pimentão/abobrinha')
                save_reviews(self.menu.week_start,{gid:{'action':'choose','name':'pimentão'}})
                state.manage_menu(self.menu.week_start,'reset')
                self.assertIsNone(state.load_menu(self.menu.week_start))
                self.assertFalse(load_reviews(self.menu.week_start))
                history=state.list_menu_history(self.menu.week_start)
                self.assertEqual(len(history),1)
                self.assertEqual(history[0]['prior_status'],'approved')
                with sqlite3.connect(db) as cx:
                    row=cx.execute('SELECT shopping_reviews_json FROM weekly_menu_history').fetchone()
                self.assertIn(gid,row[0])
                state.restore_menu_version(self.menu.week_start,history[0]['version_id'])
                restored=state.load_menu(self.menu.week_start)
                self.assertEqual(restored.status,'draft')
                self.assertEqual(restored.selections,self.menu.selections)
                self.assertEqual(len(state.list_menu_history(self.menu.week_start)),1)
                self.assertFalse(load_reviews(self.menu.week_start))

    def test_revision_unlocks_only_selected_week(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/'db.sqlite3'
            with patch.object(state,'database_path',return_value=db),patch.object(settings,'JOURNAL_STATE_DIR',Path(tmp)):
                state.save_menu(self.menu)
                state.approve_menu(self.menu.week_start)
                later=self.menu.model_copy(deep=True)
                later.week_start='2026-11-16'
                state.save_menu(later)
                state.approve_menu(later.week_start)
                state.manage_menu(self.menu.week_start,'revise')
                self.assertEqual(state.load_menu(self.menu.week_start).status,'draft')
                self.assertEqual(state.load_menu(later.week_start).status,'approved')
                state.save_menu(self.menu)
                self.assertEqual(len(state.list_menu_history(self.menu.week_start)),1)
                with self.assertRaises(ValueError):state.manage_menu('2026-11-10','reset')

    def test_manual_split_stays_reproducible_and_scales_both_people(self):
        gid=group_review_id('250 g pimentão/abobrinha')
        decision=validate_resolution({'action':'split','parts':[
            {'name':'pimentão','percent':60},{'name':'abobrinha','percent':40}]})
        original=shopping_list(self.menu,self.catalog)
        resolved=shopping_list(self.menu,self.catalog,resolutions={gid:decision})
        self.assertLess(len(resolved['needs_review']),len(original['needs_review']))
        # 250 g per person × 60% = 300 g of peppers from this recipe alone.
        pepper=next(r for r in resolved['items'] if r['ingredient']=='pimentao' and r['unit']=='g')
        self.assertGreaterEqual(pepper['quantity'],300.0)
        with self.assertRaisesRegex(ValueError,'exactly 100'):
            validate_resolution({'action':'split','parts':[
                {'name':'pimentao','percent':40},{'name':'abobrinha','percent':40}]})

    def test_yield_calculates_correct_raw_weight_and_preserves_source(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'food_yields.json'
            recorded=save_yield({'product':'arroz','from_state':'cooked',
                'raw_grams':100,'prepared_grams':250,
                'method':'boiled in water','source':'weighed at home'},file=path)
            self.assertAlmostEqual(purchase_raw(1000,recorded),400.0)
            yields=load_yields(path)
            items=[{'ingredient':'arroz','state':'raw','unit':'g','quantity':300,'recipes':'dinner:01'},
                   {'ingredient':'arroz','state':'cooked','unit':'g','quantity':1000,'recipes':'lunch:01'}]
            before=supermarket_rows(items)
            self.assertTrue(before[0]['requires_conversion'])
            after=supermarket_rows(items,yields=yields)
            self.assertFalse(after[0]['requires_conversion'])
            self.assertAlmostEqual(after[0]['quantity'],700.0)
            self.assertIn('boiled in water',after[0]['note'])
            self.assertIn('weighed at home',after[0]['note'])
            with self.assertRaises(ValueError):
                validate_yield({'product':'arroz','from_state':'cooked',
                                'raw_grams':100,'prepared_grams':200,'method':'boiled','source':''})

    def test_prepared_only_product_needs_a_yield_even_when_no_raw_items(self):
        row=supermarket_rows([{'ingredient':'frango','state':'cooked','unit':'g',
                               'quantity':500,'recipes':'lunch:02'}])[0]
        self.assertTrue(row['requires_conversion'])
        self.assertIsNone(row['quantity'])

    def test_estimates_independent_and_4_4_9_consistent(self):
        user=estimate_person(weight_kg=80,height_cm=191,age=33,sex='male')
        spouse=estimate_person(weight_kg=75,height_cm=176,age=33,sex='female',
                               training_additions={'rest':0,'easy':0,'moderate':0,'long':0})
        self.assertNotEqual(user['targets']['easy']['kcal'],spouse['targets']['easy']['kcal'])
        self.assertGreater(user['targets']['long']['kcal'],user['targets']['rest']['kcal'])
        for row in user['targets'].values():
            self.assertAlmostEqual(row['kcal'],row['protein_g']*4+row['carbs_g']*4+row['fat_g']*9,delta=1)
        with self.assertRaises(ValueError):estimate_person(weight_kg=-1,height_cm=191,age=33,sex='male')

    def test_inputs_private_roundtrip(self):
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/'nutrition_inputs.json'
            save_inputs({'person_a':{'weight_kg':80}},file=file)
            self.assertEqual(load_inputs(file),{'person_a':{'weight_kg':80}})
            self.assertEqual(file.stat().st_mode & 0o777,0o600)

    def test_ui_has_all_workflows_and_no_generated_debug_dump(self):
        source=Path(__file__).resolve().parents[1]/'planner_app.py'
        code=source.read_text(encoding='utf-8')
        ast.parse(code)
        for fragment in ('manage_menu(', 'restore_menu_version(', 'save_yield(',
                         "'action':'split'", 'estimate_person(', "st.image(r.image_url"):
            self.assertIn(fragment,code)
        self.assertNotIn('st.write(st.warning(',code)

if __name__=='__main__':
    import unittest
    unittest.main()
