"""Gemini に返させる構造（JSON スキーマ）と、API の入力モデル。"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---- Gemini の構造化出力 ----
class PlanSkill(BaseModel):
    skill_id: str
    reason: str


class PlanOut(BaseModel):
    allowed: bool
    refusal_reason: str
    task_type: str
    risk_level: str  # low / medium / high
    risk_note: str
    skills: list[PlanSkill]
    starter_tip: str


class SkillScore(BaseModel):
    skill_id: str
    score: int  # 0, 1, 2
    comment: str


class ReviewOut(BaseModel):
    scores: list[SkillScore]
    good_points: list[str]
    improvements: list[str]
    improved_prompt: str


class RunOut(BaseModel):
    answer: str
    check_points: list[str]


class QuizQuestion(BaseModel):
    skill_id: str
    question: str
    choices: list[str]
    answer_index: int
    explanation: str


class QuizOut(BaseModel):
    questions: list[QuizQuestion]


# ---- API の入力 ----
class PlanIn(BaseModel):
    goal: str = Field(max_length=2000)


class ReviewIn(BaseModel):
    goal: str = Field(max_length=2000)
    skill_ids: list[str] = Field(max_length=7)
    prompt: str = Field(max_length=5000)


class RunIn(BaseModel):
    goal: str = Field(max_length=2000)
    prompt: str = Field(max_length=5000)
    risk_level: str = "low"


class QuizIn(BaseModel):
    goal: str = Field(max_length=2000)
    prompt: str = Field(max_length=5000)
    skill_ids: list[str] = Field(max_length=7)
    weak_skill_ids: list[str] = Field(default_factory=list, max_length=7)
