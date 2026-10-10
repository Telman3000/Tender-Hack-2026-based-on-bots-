from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CharSource(str, Enum):
    KTRU = "ktru"
    PORTAL = "portal"
    NEW = "new"
    USER = "user"  # legacy, not emitted anymore


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    INPUT_CONFLICT = "INPUT_CONFLICT"
    NO_MATCH_IN_SNAPSHOT = "NO_MATCH_IN_SNAPSHOT"


class CardStatus(str, Enum):
    READY = "READY"
    INCOMPLETE = "INCOMPLETE"
    HAS_UNVERIFIED_EXTRAS = "HAS_UNVERIFIED_EXTRAS"


class TextSpan(BaseModel):
    start: int
    end: int


class ParsedCharacteristic(BaseModel):
    # contract fields
    name: str = ""
    value: str
    unit: str | None = None
    source: CharSource = CharSource.NEW
    origin: Literal["ktru", "portal", "new"] = "new"
    polarity: Literal["positive", "negative"] = "positive"
    user_input: str | None = None
    required: bool = False
    allowed: list[str] | None = None
    min: float | None = None
    max: float | None = None
    # legacy
    raw_name: str = ""
    canonical_name: str = ""
    confidence: float = 1.0
    notes: str | None = None
    span: TextSpan | list[int] | None = None

    @model_validator(mode="after")
    def _sync_origin_span(self) -> ParsedCharacteristic:
        if self.source in (CharSource.KTRU, CharSource.PORTAL, CharSource.NEW):
            self.origin = self.source.value  # type: ignore[assignment]
        if isinstance(self.span, list) and len(self.span) >= 2:
            self.span = TextSpan(start=int(self.span[0]), end=int(self.span[1]))
        return self


class Issue(BaseModel):
    type: str = ""
    field: str | None = None
    value: str | None = None
    expected: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    message: str
    severity: str = "warning"
    span: TextSpan | list[int] | None = None
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
        if isinstance(self.span, list) and len(self.span) >= 2:
            self.span = TextSpan(start=int(self.span[0]), end=int(self.span[1]))

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
    step: int = 0
    label: str = ""
    remaining: int
    removed: int = 0
    reason: str | None = None
    removed_codes: list[str] = Field(default_factory=list)
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
    span: TextSpan | list[int] | None = None

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


class SearchInfo(BaseModel):
    snapshot_id: str | None = None
    domain: str | None = None
    area_size: int = 0
    checked_count: int = 0
    compatible_count: int = 0
    completeness: Literal["full", "partial"] = "partial"
    # codes before final char elimination (name shortlist) — for QA completeness
    shortlist: list[str] = Field(default_factory=list)


class CharCheck(BaseModel):
    code: str
    char_name: str
    outcome: Literal["PASS", "FAIL", "UNKNOWN"]
    reason: str | None = None


class Question(BaseModel):
    field: str | None = None
    reason: str = ""
    options: list[str] = Field(default_factory=list)
    eliminates: int = 0


class ProductMention(BaseModel):
    mention: str
    start: int
    end: int
    reason: str = ""


class Candidate(BaseModel):
    code: str
    name: str
    score: float


def derive_legacy_status(
    match_status: MatchStatus | str,
    card_status: CardStatus | str,
    distinct_name_count: int,
) -> str:
    ms = match_status.value if isinstance(match_status, MatchStatus) else match_status
    cs = card_status.value if isinstance(card_status, CardStatus) else card_status
    if ms == MatchStatus.NO_MATCH_IN_SNAPSHOT.value:
        return "not_found"
    if ms == MatchStatus.INPUT_CONFLICT.value:
        return "error"
    if ms == MatchStatus.NEEDS_CLARIFICATION.value and distinct_name_count > 1:
        return "ambiguous"
    if ms == MatchStatus.NEEDS_CLARIFICATION.value or (
        ms == MatchStatus.MATCHED.value and cs == CardStatus.INCOMPLETE.value
    ):
        return "need_more"
    if ms == MatchStatus.MATCHED.value and cs in (
        CardStatus.READY.value,
        CardStatus.HAS_UNVERIFIED_EXTRAS.value,
    ):
        return "ok"
    return "need_more"


class AnalyzeResponse(BaseModel):
    input_text: str
    detected_domain: str | None
    product_guess: str | None
    characteristics: list[ParsedCharacteristic]
    issues: list[Issue]
    narrowing: list[NarrowingStep]
    best_ktru: KtruCandidate | None
    candidates: list[Candidate] = Field(default_factory=list)
    # Person-1 contract
    match_status: MatchStatus = MatchStatus.NEEDS_CLARIFICATION
    card_status: CardStatus = CardStatus.INCOMPLETE
    search: SearchInfo = Field(default_factory=SearchInfo)
    checks: list[CharCheck] = Field(default_factory=list)
    question: Question | None = None
    ambiguities: list[ProductMention] = Field(default_factory=list)
    # legacy
    status: str
    code_status: Literal["determined", "ambiguous", "not_found"] = "not_found"
    completeness: Completeness = Field(default_factory=Completeness)
    corrections: list[Correction] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    next_steps_detail: list[NextStep] = Field(default_factory=list)
    debug: dict[str, Any] = Field(default_factory=dict)
