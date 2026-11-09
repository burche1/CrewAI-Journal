"""v0.4 regression tests: image cards, expandable catalogs, market grouping, reviews."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import ast

from src.journal_core.grocery import product_name, section_for, supermarket_rows
from src.journal_core.recipe_parser import load_catalog, parse_recipe_file
from src.journal_core.reviews import group_review_id, validate_resolution
from src.journal_core.shopping import shopping_list, as_markdown, as_csv
from src.journal_core.weekly import create_menu


class CoreV04Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=load_catalog()
        cls.menu=create_menu(date(2026,11,9),cls.catalog,
                             {cat:[r.id for r in recipes[:7]]
                              for cat, recipes in cls.catalog.items()})

    def test_image_urls_from_all_120_markdown_recipes(self):
        self.assertEqual(sum(len(v) for v in self.catalog.values()),120)
        for recipes in self.catalog.values():
            self.assertEqual(sum(bool(r.image_url) for r in recipes),len(recipes))
            for r in recipes:self.assertTrue(r.image_url.startswith('https://'))

    def test_catalog_accepts_100th_recipe_without_code_changes(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'Breakfast.md'
            path.write_text('''# Recipes\n\n### 100. Future recipe\n\n![Future](https://example.com/food.jpg)\n\n**Você:** 200 g iogurte.\n\n**Esposa:** 150 g iogurte.\n\n**Modo de preparo:** Combine.\n''',encoding='utf-8')
            rows=parse_recipe_file(path,'breakfast')
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0].id,'breakfast:100')
            self.assertEqual(rows[0].image_url,'https://example.com/food.jpg')

    def test_count_units_not_repeated_review_prompts(self):
        menu=self.menu.model_copy(deep=True)
        menu.portion_factors={'person_a':1.15,'person_b':1.1}
        result=shopping_list(menu,self.catalog)
        for r in result['needs_review']:
            self.assertNotIn('fractional',r['reason'].lower())
            self.assertNotIn('ovos',r['ingredient'].casefold())
        eggs=[r for r in result['supermarket'] if r['ingredient']=='ovo']
        self.assertEqual(len(eggs),1)
        self.assertIsInstance(eggs[0]['quantity'],int)
        self.assertEqual(eggs[0]['section'],'Käse, Eier & Molkerei')

    def test_german_aisles_product_aliases_and_milk(self):
        result=shopping_list(self.menu,self.catalog)
        market=result['supermarket']
        milk=[r for r in market if r['ingredient']=='leite' and r['unit']=='ml']
        self.assertEqual(len(milk),1)
        self.assertGreater(milk[0]['quantity'],700)
        self.assertEqual(section_for('maca'),'Obst & Gemüse')
        self.assertEqual(section_for('arroz'),'Reis, Nudeln & Getreide')
        self.assertEqual(product_name('file de salmao'),'salmao')
        self.assertEqual(len([r for r in market if r['ingredient']=='azeite']),1)
        self.assertEqual(len([r for r in market if r['ingredient']=='salmao']),1)

    def test_raw_cooked_never_silently_added(self):
        result=shopping_list(self.menu,self.catalog)
        rice=next(r for r in result['supermarket'] if r['ingredient']=='arroz')
        self.assertIsNone(rice['quantity'])
        self.assertTrue(rice['requires_conversion'])
        self.assertIn('raw',rice['states'])
        self.assertIn('cooked',rice['states'])
        self.assertGreater(result['conversion_count'],0)
        self.assertFalse(result['shopping_ready'])

    def test_review_groups_are_fewer_than_raw_rows(self):
        result=shopping_list(self.menu,self.catalog)
        self.assertLess(len(result['review_groups']),len(result['needs_review']))
        self.assertTrue(all(g['count']>=1 for g in result['review_groups']))
        self.assertEqual(group_review_id('120 g pimentão/abobrinha'),
                         group_review_id('250 g pimentão/abobrinha'))

    def test_choice_applies_source_amounts_both_people(self):
        before=self.menu.model_dump()
        initial=shopping_list(self.menu,self.catalog)
        group=next(g for g in initial['review_groups'] if 'pimentão/abobrinha' in g['ingredient'])
        revised=shopping_list(self.menu,self.catalog,
                              resolutions={group['group_id']:{'action':'choose','name':'pimentao'}})
        self.assertEqual(len(revised['needs_review']),len(initial['needs_review'])-group['count'])
        self.assertEqual(revised['reviewed'],group['count'])
        self.assertEqual(self.menu.model_dump(),before)
        pepper=next(row for row in revised['supermarket'] if row['ingredient']=='pimentao')
        self.assertGreater(pepper['quantity'],0)

    def test_aisle_markdown_checklist_and_csv(self):
        result=shopping_list(self.menu,self.catalog)
        md=as_markdown(result)
        self.assertIn('Shopping list',md)
        self.assertIn('## Obst & Gemüse',md)
        self.assertIn('## Käse, Eier & Molkerei',md)
        self.assertIn('- [ ] **',md)
        self.assertIn('Roh-/Gargewicht prüfen',md)
        csv=as_csv(result)
        self.assertIn('section,ingredient,label,quantity_display',csv)
        self.assertIn('Obst & Gemüse',csv)

    def test_legacy_review_resolution_and_choose_validation(self):
        self.assertEqual(validate_resolution({'action':'choose','name':'pimentão'}),
                         {'action':'choose','name':'pimentao'})
        self.assertEqual(validate_resolution({'action':'skip'}),{'action':'skip'})
        with self.assertRaises(ValueError):
            validate_resolution({'action':'choose','name':'pepino/tomate'})

    def test_planner_is_valid_python_without_magic_conditional_log_output(self):
        app=Path(__file__).resolve().parents[1]/'planner_app.py'
        code=app.read_text(encoding='utf-8')
        ast.parse(code)
        self.assertNotIn('st.warning(f"{len(shopping[\'needs_review\'])}',code)
        self.assertIn("st.image(r.image_url",code)
        self.assertIn('st.rerun()',code)


if __name__=='__main__':
    import unittest
    unittest.main()
