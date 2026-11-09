"""Structured outputs. Original source strings remain intact for auditing."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    raw: str
    name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    measurement_state: Literal["raw", "cooked", "drained", "as_served", "unknown"] = "unknown"
    optional: bool = False
    ambiguous: bool = False
    issues: list[str] = Field(default_factory=list)


class Recipe(BaseModel):
    id: str
    category: Literal["breakfast", "lunch", "dinner", "snacks"]
    number: int = Field(ge=1)
    title: str
    source_file: str
    source_sha256: str
    source_start_line: int = Field(ge=1)
    source_end_line: int = Field(ge=1)
    portions: dict[str, str]  # person_a / person_b: exact literal lines
    ingredients: dict[str, list[Ingredient]]
    preparation: str | None = None
    organization: str | None = None
    details: dict[str, str] = Field(default_factory=dict)
    markdown: str
    image_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


class DailyTraining(BaseModel):
    date: str
    weekday: str
    week: str
    phase: str
    endurance: str
    morning: str
    gym_workout: str | None = None
    gym_progression: str | None = None
    gym_exercises: list[dict[str, str]] = Field(default_factory=list)
    optional: bool = False
    sources: dict[str, str]
    notes: list[str] = Field(default_factory=list)


class WeeklyMenu(BaseModel):
    week_start: str
    status: Literal["draft", "approved"] = "draft"
    selections: dict[str, list[str]]
    source_hashes: dict[str, str] = Field(default_factory=dict)
    updated_at: str | None = None
    portion_factors: dict[str, float] = Field(default_factory=lambda: {"person_a": 1.0, "person_b": 1.0})
