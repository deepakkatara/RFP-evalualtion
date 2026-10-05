from __future__ import annotations

from datetime import date
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class Criterion(BaseModel):
    criterion_id: int
    name: str
    description: str
    weight: float = Field(gt=0)
    max_score: float = Field(gt=0)
    is_active: bool = True


class CriterionEvaluation(BaseModel):
    criterion_id: int
    score: float
    max_score: float
    justification: str = ""
    evidence: str = ""
    evidence_page: Optional[int] = None
    evidence_verified: bool = False
    confidence: float = Field(default=0.0, ge=0, le=1)


class LLMScorecard(BaseModel):
    supplier_name: str
    criteria: list[CriterionEvaluation]
    risks: list[str] = Field(default_factory=list)
    overall_summary: str = ""


class SupplierInput(BaseModel):
    supplier_name: str
    submission_date: date
    experience_rating: float = Field(ge=0)
    document_text: str

    @field_validator("supplier_name")
    @classmethod
    def name_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("supplier name is required")
        return value.strip()


class ValidatedSupplier(BaseModel):
    supplier: SupplierInput
    scorecard: LLMScorecard
    warnings: list[str] = Field(default_factory=list)


class RankedSupplier(BaseModel):
    supplier_name: str
    submission_date: date
    experience_rating: float
    absolute_score: float
    ppi: float
    final_rank: int
    criteria: list[dict[str, Any]]
    risks: list[str]
    overall_summary: str
    warnings: list[str]
    evidence_coverage: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    review_required: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    tie_break_explanation: str
