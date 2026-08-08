"""Веб-API поверх RAG-пайплайна: python -m nomus.api.main

Тот же оркестратор, что и в боте, — правила безопасности (abstention,
валидация цитат, red-flag, safety-режим) действуют одинаково в обоих каналах.
"""

import io
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from nomus import db
from nomus.api.clientip import client_ip
from nomus.api.schemas import AskRequest, AskResponse, ClaimRequest, SourceRef
from nomus.bot.render import DISCLAIMER
from nomus.config import settings
from nomus.contacts import CONTACTS
from nomus.docgen import ClaimFields, build_claim_docx
from nomus.pipeline.orchestrator import process_query
from nomus.schemas import PipelineResult, RiskProfile, UserProfile

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Простой in-memory rate limit: демо не должно уводить бюджет OpenAI в минус.
_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= settings.rate_limit_per_hour:
        return True
    q.append(now)
    return False


async def _warmup() -> None:
    """Прогрев ML-моделей до первого запроса (NFR-01, NFR-04)."""
    import asyncio

    def _load() -> None:
        from nomus.pipeline.reranker import rerank
        from nomus.pipeline.retriever import retrieve

        rerank("прогрев", retrieve("невыплата заработной платы", top_k=3))

    log.info("Прогреваю модели…")
    try:
        await asyncio.to_thread(_load)
        log.info("Модели готовы")
    except Exception:
        log.exception("Прогрев не удался — продолжаю без него")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    db.init_db()
    await _warmup()
    yield


app = FastAPI(
    title="Nomus AI API",
    description="Правовая информация о трудовых правах мигрантов в РК со ссылками на НПА",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "bot_url": settings.bot_url}


@app.get("/api/contacts")
async def contacts() -> dict:
    return {"contacts": CONTACTS, "bot_url": settings.bot_url}


def _to_response(result: PipelineResult, profile: UserProfile) -> AskResponse:
    sources = [
        SourceRef(
            doc_short=rc.chunk.doc_short,
            article_num=rc.chunk.article_num,
            article_title=rc.chunk.article_title,
            url=rc.chunk.url,
            score=round(rc.score, 3),
        )
        for rc in result.retrieved
    ]
    resp = AskResponse(
        kind=result.kind,
        red_flag=result.red_flag,
        red_flag_triggers=result.red_flag_triggers,
        abstain_reason=result.abstain_reason,
        sources=sources,
        latency_ms=result.latency_ms,
        disclaimer=DISCLAIMER,
    )
    if result.answer:
        a = result.answer
        resp.summary = a.summary
        resp.rights = a.rights
        resp.risk_warning = a.risk_warning
        resp.action_plan = a.action_plan
        resp.contacts = a.contacts
        resp.offer_document = a.offer_document
        # FR-24: страховка, если LLM не вернул предупреждение для UNDOCUMENTED
        if not a.risk_warning and profile.effective_risk == RiskProfile.UNDOCUMENTED:
            resp.risk_warning = (
                "У вас нет подтверждённых документов. Обращение в государственные органы "
                "может повлечь проверку вашего статуса. Сначала посоветуйтесь с НПО "
                "или консульством вашей страны."
            )
    return resp


@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest, request: Request) -> AskResponse:
    if _rate_limited(client_ip(request)):
        raise HTTPException(429, "Слишком много запросов. Попробуйте через час или напишите боту.")

    profile = UserProfile(citizenship=req.citizenship, risk=req.risk)
    result = await process_query(req.question, profile)

    # Приватность: в лог идёт только хеш вопроса (§7 ТЗ)
    db.log_query(
        user_id=0,
        query_text=req.question,
        retrieved_ids=[rc.chunk.chunk_id for rc in result.retrieved],
        confidence=result.answer.confidence if result.answer else "n/a",
        red_flag=result.red_flag,
        abstained=result.kind == "abstain",
        latency_ms=result.latency_ms,
    )
    return _to_response(result, profile)


@app.post("/api/claim")
async def claim(req: ClaimRequest, request: Request) -> StreamingResponse:
    """Генерация заявления .docx. Поля не сохраняются — только рендер в файл."""
    if _rate_limited(client_ip(request)):
        raise HTTPException(429, "Слишком много запросов. Попробуйте позже.")

    fields = ClaimFields(**req.model_dump())
    try:
        data = build_claim_docx(fields)
    except Exception:
        log.exception("docx generation failed")
        raise HTTPException(500, "Не удалось сформировать документ")

    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="zayavlenie.docx"'},
    )


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(WEB_DIR / "index.html"))


def main() -> None:
    import uvicorn

    uvicorn.run(
        "nomus.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        # За cloudflared/nginx: без этого uvicorn считает схему http и
        # отдаёт неверные абсолютные URL в редиректах.
        proxy_headers=settings.trusted_proxy,
        forwarded_allow_ips="*" if settings.trusted_proxy else None,
    )


if __name__ == "__main__":
    main()
