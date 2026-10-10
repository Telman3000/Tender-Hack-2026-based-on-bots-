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
    span: list[int] | None = None  # [start, end) in the original text when the value came from it
    suspicious: bool = False  # the characteristic does not fit the item type (see issue type=mismatch)


class Issue(BaseModel):
    # contract fields
    type: str = ""  # not_allowed | out_of_range | unit | mismatch | missing | typo (+ ambiguous, new_property)
    field: str | None = None
    value: str | None = None
    expected: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    message: str
    severity: str = "warning"  # error | warning
    span: list[int] | None = None  # [start, end) in the original text, or null
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


class Correction(BaseModel):
    field: str | None = None
    kind: Literal["unit", "autofix", "typo", "translit"]
    from_: str = Field(alias="from")
    to: str
    span: list[int] | None = None

    model_config = {"populate_by_name": True}


class NextStep(BaseModel):
    text: str
    field: str | None = None
    required: bool = False


class Completeness(BaseModel):
    required_total: int = 0
    required_filled: int = 0
    optional_total: int = 0
    optional_filled: int = 0


class MissingCharacteristic(BaseModel):
    """A characteristic of the chosen KTRU code that is not filled yet."""
    name: str
    required: bool
    allowed: list[str] | None = None  # enum values from KTRU
    min: float | None = None
    max: float | None = None
    unit: str | None = None


class FillCounter(BaseModel):
    """«заполнено X из Y» over the characteristics of the chosen KTRU code."""
    filled: int = 0
    total: int = 0
    required_filled: int = 0
    required_total: int = 0
    text: str = ""


class Question(BaseModel):
    """Asked only when the choice cannot be made for the user (several names / a required enum splits codes)."""
    field: str
    reason: str
    options: list[str] = Field(default_factory=list)  # <= 6, values from KTRU only
    remaining_by_option: dict[str, int] = Field(default_factory=dict)  # codes left after choosing the option
    candidates_now: int = 0


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
    status: str  # legacy: ok | need_more | ambiguous | error | not_found
    code_status: Literal["determined", "ambiguous", "not_found"] = "not_found"
    card_status: Literal["complete", "incomplete", "invalid"] = "incomplete"
    completeness: Completeness = Field(default_factory=Completeness)
    corrections: list[Correction] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)  # required steps only
    next_steps_detail: list[NextStep] = Field(default_factory=list)
    missing_characteristics: list[MissingCharacteristic] = Field(default_factory=list)  # required first
    fill: FillCounter = Field(default_factory=FillCounter)
    question: Question | None = None
    out_of_scope: bool = False
    message: str | None = None
    debug: dict[str, Any] = Field(default_factory=dict)
