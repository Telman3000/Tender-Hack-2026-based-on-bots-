from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CharSource(str, Enum):
    KTRU = "ktru"
    PORTAL = "portal"
    NEW = "new"
    USER = "user"  # legacy, not emitted anymore


class ParsedCharacteristic(BaseModel):
    # contract fields
    name: str = ""
    value: str
    unit: str | None = None
    source: CharSource = CharSource.NEW
    user_input: str | None = None
    required: bool = False
    allowed: list[str] | None = None  # enum values from KTRU (None for numeric / free)
    min: float | None = None  # numeric range from KTRU, in `unit`
    max: float | None = None
    # legacy fields (kept for backward compatibility)
    raw_name: str = ""
    canonical_name: str = ""
    confidence: float = 1.0
    notes: str | None = None


class Issue(BaseModel):
    # contract fields
    type: str = ""  # not_allowed | out_of_range | unit | mismatch | missing | typo (+ ambiguous, new_property)
    field: str | None = None
    value: str | None = None
    expected: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    message: str
    severity: str = "warning"  # error | warning
    # legacy
    kind: str = ""
    suggestion: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if not self.type:
            self.type = self.kind
        if not self.kind:
            self.kind = self.type
        if self.suggestion and not self.suggestions:
            self.suggestions = [self.suggestion]
        if not self.suggestion and self.suggestions:
            self.suggestion = self.suggestions[0]
        self.suggestions = self.suggestions[:3]

    @classmethod
    def make(cls, type: str, message: str, **kw: Any) -> "Issue":
        return cls(type=type, kind=type, message=message, **kw)


class KtruCandidate(BaseModel):
    code: str
    name: str
    okpd2: str | None = None
    score: float
    required_chars: list[str] = Field(default_factory=list)
    matched_chars: list[str] = Field(default_factory=list)


class NarrowingStep(BaseModel):
    # contract fields
    step: int = 0
    label: str = ""
    remaining: int
    removed: int = 0
    reason: str | None = None
    removed_codes: list[str] = Field(default_factory=list)
    # legacy
    stage: str = ""
    top: list[KtruCandidate] = Field(default_factory=list)
    note: str | None = None


class InputCharacteristic(BaseModel):
    name: str
    value: str | None = ""
    unit: str | None = None


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Свободное описание товара")
    domain_hint: Literal["furniture", "clothing", "tools"] | None = Field(
        default=None, description="furniture | clothing | tools | null"
    )

    @field_validator("domain_hint", mode="before")
    @classmethod
    def _empty_hint(cls, v: Any) -> Any:
        return None if v in ("", None) else v
    characteristics: list[InputCharacteristic] | None = Field(
        default=None, description="Явно заданные характеристики — перекрывают распознанные из текста"
    )


class Candidate(BaseModel):
    code: str
    name: str
    score: float


class AnalyzeResponse(BaseModel):
    input_text: str
    detected_domain: str | None
    product_guess: str | None
    characteristics: list[ParsedCharacteristic]
    issues: list[Issue]
    narrowing: list[NarrowingStep]
    best_ktru: KtruCandidate | None
    candidates: list[Candidate] = Field(default_factory=list)
    status: str  # ok | need_more | ambiguous | error
    next_steps: list[str] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)
