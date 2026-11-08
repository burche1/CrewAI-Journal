"""v0.2 regression tests: offline, no legacy journal execution."""
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from src.journal_core import state
from src.journal_core.recipe_parser import load_catalog, get_recipe, split_portion_ingredients
from src.journal_core.schedule import (CYCLE,anchor_training,week_for_date,pause_training,resume_training,get_schedule)
from src.journal_core.shopping import shopping_list,as_csv,as_markdown
from src.journal_core.nutrition import week_nutrition, load_reference,recipe_nutrition
from src.journal_core.weekly import create_menu


class CoreV02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog()

    def test_parenthetical_comma_kept_together(self):
        chunks=split_portion_ingredients('400 g chili pronto (com carne, feijão e tomate), 260 g arroz cozido, 25 g queijo')
        self.assertEqual(len(chunks),3)
        r=get_recipe(self.catalog,'lunch:04')
        self.assertEqual(len(r.ingredients['person_a']),3)
        self.assertIn('feijão e tomate',r.ingredients['person_a'][0].name)

    def test_calendar_advances_without_writes(self):
        with TemporaryDirectory() as tmp:
            db=Path(tmp)/'journal.sqlite3'
            with patch('src.journal_core.state.database_path', return_value=db):
                self.assertIsNone(get_schedule())
                anchor_training(date(2026,11,9),'P1')
                for d,week in [(date(2026,11,9),'P1'),(date(2026,11,16),'P2'),
                               (date(2026,11,30),'P4'),(date(2026,12,7),'1'),
                               (date(2027,11,29),'52')]:
                    self.assertEqual(week_for_date(d)['week'],week)
                self.assertTrue(week_for_date(date(2027,12,6))['complete'])
                before=db.stat().st_mtime_ns
                week_for_date(date(2026,11,17))
                self.assertEqual(db.stat().st_mtime_ns,before)

    def test_pause_resume_and_override(self):
        with TemporaryDirectory() as tmp:
            with patch('src.journal_core.state.database_path',return_value=Path(tmp)/'db.sqlite3'):
                anchor_training(date(2026,11,9),'P1')
                pause_training(date(2026,11,24))
                self.assertEqual(week_for_date(date(2026,12,21))['week'],'P3')
                self.assertEqual(week_for_date(date(2026,12,21))['source'],'paused')
                resume_training(date(2026,12,28))
                self.assertEqual(week_for_date(date(2027,1,4))['week'],'P4')
                anchor_training(date(2027,1,11),'P2')
                self.assertEqual(week_for_date(date(2027,1,18))['week'],'P3')
                with self.assertRaises(ValueError):
                    resume_training(date(2027,1,18))

    def test_shopping_math_and_coffee_milk(self):
        selection={category:[r.id for r in recipes[:7]] for category,recipes in self.catalog.items()}
        menu=create_menu(date(2026,11,9),self.catalog,selection)
        result=shopping_list(menu,self.catalog)
        milk=next(x for x in result['items'] if x['ingredient']=='leite (cafe)')
        self.assertEqual(milk['quantity'],700)
        self.assertTrue(any(x['ingredient']=='arroz' and x['state']=='raw' for x in result['items']))
        self.assertTrue(any(x['ingredient']=='arroz' and x['state']=='cooked' for x in result['items']))
        self.assertTrue(result['needs_review'])
        self.assertNotIn('chili pronto (com carne',str(result['items']))
        self.assertIn('ingredient',as_csv(result))
        self.assertIn('# Shopping list',as_markdown(result))
        menu.portion_factors={'person_a':1.2,'person_b':1.0}
        bigger=shopping_list(menu,self.catalog)
        self.assertGreater(next(x['quantity'] for x in bigger['items'] if x['ingredient']=='aveia'),
                           next(x['quantity'] for x in result['items'] if x['ingredient']=='aveia'))

    def test_macro_subtotals_warn_on_missing_items(self):
        r=get_recipe(self.catalog,'breakfast:01')
        result=recipe_nutrition(r,'person_a',reference=load_reference())
        self.assertGreater(result['known_subtotal']['kcal'],0)
        self.assertTrue(result['matched_items']<=result['total_items'])
        selection={category:[row.id for row in rows[:7]] for category,rows in self.catalog.items()}
        menu=create_menu(date(2026,11,9),self.catalog,selection)
        totals=week_nutrition(menu,self.catalog)
        self.assertEqual(len(totals['days']),7)
        self.assertFalse(totals['days'][0]['persons']['person_a']['complete'])
        self.assertIn('NOT validated',totals['warning'])

    def test_v01_db_schema_auto_migrates_and_preserves_menu(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'old.sqlite3'
            with closing(sqlite3.connect(p)) as cx:
                cx.execute('''CREATE TABLE weekly_menus (week_start TEXT PRIMARY KEY, status TEXT NOT NULL,
                           selections_json TEXT NOT NULL,source_hashes_json TEXT NOT NULL,updated_at TEXT NOT NULL)''')
                cx.execute('''INSERT INTO weekly_menus VALUES ('2026-11-09','draft','{}','{}','old')''')
                cx.commit()
            with patch('src.journal_core.state.database_path',return_value=p):
                old=state.load_menu('2026-11-09')
                self.assertEqual(old.portion_factors,{'person_a':1.0,'person_b':1.0})
                anchor_training(date(2026,11,9),'P1')
                self.assertEqual(state.load_menu('2026-11-09').status,'draft')
                with closing(sqlite3.connect(p)) as cx:
                    columns={x[1] for x in cx.execute('PRAGMA table_info(weekly_menus)')}
                self.assertIn('portion_factors_json',columns)


if __name__ == '__main__':
    unittest.main()
