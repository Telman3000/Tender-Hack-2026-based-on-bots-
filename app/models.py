from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CharSource(str, Enum):
    KTRU = "ktru"
    PORTAL = "portal"
    NEW = "new"
    USER = "user"


class ParsedCharacteristic(BaseModel):
    raw_name: str
    canonical_name: str
    value: str
    unit: str | None = None
    source: CharSource = CharSource.USER
    confidence: float = 1.0
    notes: str | None = None


class Issue(BaseModel):
    kind: str  # missing | typo | mismatch | unit | ambiguous
    message: str
    field: str | None = None
    suggestion: str | None = None


class KtruCandidate(BaseModel):
    code: str
    name: str
    okpd2: str | None = None
    score: float
    required_chars: list[str] = Field(default_factory=list)
    matched_chars: list[str] = Field(default_factory=list)


class NarrowingStep(BaseModel):
    stage: str
    remaining: int
    top: list[KtruCandidate]
    note: str | None = None


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Свободное описание товара")
    domain_hint: str | None = Field(
        default=None,
        description="furniture | clothing | tools | null",
    )


class AnalyzeResponse(BaseModel):
    input_text: str
    detected_domain: str | None
    product_guess: str | None
    characteristics: list[ParsedCharacteristic]
    issues: list[Issue]
    narrowing: list[NarrowingStep]
    best_ktru: KtruCandidate | None
    status: str  # ok | need_more | ambiguous | error
    next_steps: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)
