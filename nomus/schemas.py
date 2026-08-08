"""Pydantic-схемы: профиль пользователя, чанк корпуса, ответ LLM (§6.4 ТЗ)."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CitizenshipProfile(str, Enum):
    EAEU = "EAEU"
    NON_EAEU = "NON_EAEU"
    UNKNOWN = "UNKNOWN"


class RiskProfile(str, Enum):
    DOCUMENTED = "DOCUMENTED"
    UNDOCUMENTED = "UNDOCUMENTED"
    UNKNOWN = "UNKNOWN"


class UserProfile(BaseModel):
    citizenship: CitizenshipProfile = CitizenshipProfile.UNKNOWN
    risk: RiskProfile = RiskProfile.UNKNOWN

    @property
    def effective_risk(self) -> RiskProfile:
        """UNKNOWN трактуем консервативно, как UNDOCUMENTED (§2.2 ТЗ)."""
        if self.risk == RiskProfile.UNKNOWN:
            return RiskProfile.UNDOCUMENTED
        return self.risk


class Chunk(BaseModel):
    """Схема чанка корпуса НПА (§5.2 ТЗ)."""

    chunk_id: str
    text: str
    parent_text: str = ""
    doc_title: str
    doc_short: str
    doc_id: str = ""
    chapter: str = ""
    article_num: str
    article_title: str = ""
    point_num: str = ""
    revision_date: str = ""
    status: str = "active"
    url: str = ""
    lang: str = "ru"
    audience: list[str] = Field(default_factory=lambda: ["all"])


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


class RightStatement(BaseModel):
    statement: str
    article: str
    doc_short: str


class ActionStep(BaseModel):
    step: int
    action: str
    why: str = ""


class Answer(BaseModel):
    """ANSWER_SCHEMA (§6.4 ТЗ)."""

    confidence: str = Field(pattern="^(high|medium|low)$")
    summary: str
    rights: list[RightStatement] = Field(default_factory=list)
    risk_warning: Optional[str] = None
    action_plan: list[ActionStep] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    red_flag: bool = False
    offer_document: Optional[str] = None


class PipelineResult(BaseModel):
    """Итог работы оркестратора для рендера в Telegram."""

    kind: str  # "answer" | "abstain" | "red_flag_priority" | "error"
    answer: Optional[Answer] = None
    red_flag: bool = False
    red_flag_triggers: list[str] = Field(default_factory=list)
    abstain_reason: Optional[str] = None
    retrieved: list[RetrievedChunk] = Field(default_factory=list)
    latency_ms: int = 0
