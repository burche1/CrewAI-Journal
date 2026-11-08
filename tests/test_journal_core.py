"""Offline integration tests run against YOUR configured six Markdown files.

No network, CrewAI, Google OAuth, reading progression, or journal_v3 execution.
"""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.journal_core.recipe_parser import load_catalog, get_recipe
from src.journal_core.training_parser import load_training
from src.journal_core.weekly import create_menu, day_menu
from src.journal_core import state


class SourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.training = load_training()

    def test_recipe_counts_and_portions(self):
        self.assertEqual({k: len(r) for k, r in self.catalog.items()},
                         {"breakfast": 30, "lunch": 30, "dinner": 30, "snacks": 30})
        for rows in self.catalog.values():
            for recipe in rows:
                self.assertEqual(set(recipe.portions), {"person_a", "person_b"})
                self.assertTrue(recipe.preparation)
                self.assertTrue(recipe.organization)
                self.assertEqual(set(recipe.ingredients), {"person_a", "person_b"})
                self.assertTrue(recipe.ingredients["person_a"])
                self.assertTrue(recipe.ingredients["person_b"])

    def test_ingredient_split_not_just_one_large_item(self):
        oats = get_recipe(self.catalog, "breakfast:01")
        self.assertEqual(oats.title, "Overnight oats")
        self.assertEqual(len(oats.ingredients["person_a"]), 5)
        self.assertEqual(oats.ingredients["person_a"][0].quantity, 90)
        self.assertEqual(oats.ingredients["person_a"][0].unit, "g")
        self.assertEqual(oats.ingredients["person_a"][0].name, "aveia")

    def test_source_ambiguity_is_not_silently_resolved(self):
        r = get_recipe(self.catalog, "dinner:01")
        self.assertTrue(any(i.ambiguous for i in r.ingredients["person_a"]))

    def test_training_preparation_and_main_cycle(self):
        self.assertEqual(len(self.training.prep), 4)
        self.assertEqual(len(self.training.main), 50)
        self.assertEqual(len(self.training.gym_days), 7)
        preview = self.training.preview(date(2026, 11, 10), "P1")
        self.assertIn("Bike 20 min", preview.endurance)
        self.assertIn("1 set each", preview.gym_progression)
        self.assertEqual(preview.gym_workout, "Strength A")
        week1 = self.training.preview(date(2026, 11, 10), "1")
        self.assertIn("45 min", week1.endurance)

    def test_race_and_recovery_mornings(self):
        race_sunday = self.training.preview(date(2026, 11, 15), "51")
        self.assertIn("IRONMAN", race_sunday.endurance)
        self.assertIsNone(race_sunday.gym_workout)
        recovery_friday = self.training.preview(date(2026, 11, 13), "52")
        self.assertIn("Optional", recovery_friday.endurance)
        self.assertIsNone(recovery_friday.gym_workout)

    def test_all_prep_and_cycle_weeks_every_day(self):
        monday = date(2026, 11, 9)
        from datetime import timedelta
        for week in ["P1", "P2", "P3", "P4"] + [str(i) for i in range(1, 53)]:
            for day in range(7):
                snapshot = self.training.preview(monday + timedelta(days=day), week)
                self.assertEqual(snapshot.week, week)
                self.assertTrue(snapshot.endurance)

    def test_weekly_plan_draft(self):
        selections = {cat: [r.id for r in rows[:7]] for cat, rows in self.catalog.items()}
        menu = create_menu(date(2026, 11, 9), self.catalog, selections)
        self.assertEqual(menu.status, "draft")
        today = day_menu(date(2026, 11, 10), menu, self.catalog)
        self.assertEqual(today["meals"]["breakfast"]["id"], "breakfast:02")
        self.assertFalse(today["source_changed"])

    def test_state_does_not_advance_and_approved_week_is_locked(self):
        selections = {cat: [r.id for r in rows[:7]] for cat, rows in self.catalog.items()}
        menu = create_menu(date(2026, 11, 9), self.catalog, selections)
        with TemporaryDirectory() as tmp:
            with patch("src.journal_core.state.database_path", return_value=Path(tmp) / "private.sqlite3"):
                self.assertIsNone(state.get_week())
                state.set_week("P1", "Starting safely")
                self.assertEqual(state.get_week()[0], "P1")
                state.save_menu(menu)
                state.approve_menu(menu.week_start)
                self.assertEqual(state.load_menu(menu.week_start).status, "approved")
                with self.assertRaises(ValueError):
                    state.save_menu(menu)
                self.assertEqual(state.get_week()[0], "P1")


if __name__ == "__main__":
    unittest.main()
