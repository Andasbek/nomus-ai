"""Схемы запросов и ответов веб-API."""

from typing import Optional

from pydantic import BaseModel, Field

from nomus.schemas import ActionStep, CitizenshipProfile, RightStatement, RiskProfile


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    citizenship: CitizenshipProfile = CitizenshipProfile.UNKNOWN
    risk: RiskProfile = RiskProfile.UNKNOWN


class SourceRef(BaseModel):
    doc_short: str
    article_num: str
    article_title: str = ""
    url: str = ""
    score: float


class AskResponse(BaseModel):
    """Ответ пайплайна в форме, пригодной для рендера на фронте."""

    kind: str  # answer | abstain | error
    summary: Optional[str] = None
    rights: list[RightStatement] = Field(default_factory=list)
    risk_warning: Optional[str] = None
    action_plan: list[ActionStep] = Field(default_factory=list)
    contacts: list[str] = Field(default_factory=list)
    red_flag: bool = False
    red_flag_triggers: list[str] = Field(default_factory=list)
    offer_document: Optional[str] = None
    abstain_reason: Optional[str] = None
    sources: list[SourceRef] = Field(default_factory=list)
    latency_ms: int = 0
    disclaimer: str


class ClaimRequest(BaseModel):
    """Поля заявления. Не сохраняются на сервере — только рендер в .docx."""

    full_name: str = Field(max_length=200)
    citizenship: str = Field(max_length=100)
    employer: str = Field(max_length=300)
    work_period: str = Field(max_length=100)
    debt_amount: str = Field(max_length=50)
    contact: str = Field(max_length=200)
    violated_articles: list[str] = Field(default_factory=list, max_length=20)
