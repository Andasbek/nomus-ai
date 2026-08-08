"""Оркестратор пайплайна ответа (§6.1 ТЗ):
Profiler → Red-flag → Rewriter → Retrieval → Rerank → Generate → Validate.

Graceful degradation (NFR-06): любая ошибка → kind="error" с контактами помощи.
"""

import asyncio
import logging
import time

from nomus.config import settings
from nomus.pipeline import redflag, rewriter
from nomus.pipeline.generator import generate_answer
from nomus.pipeline.validator import validate_citations, validate_required_fields
from nomus.schemas import PipelineResult, UserProfile

log = logging.getLogger(__name__)

_openai_client = None


def get_openai():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def process_query(question: str, profile: UserProfile) -> PipelineResult:
    started = time.monotonic()

    def _elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    # 2. Red-flag детектор: ключевые слова (мгновенно) + LLM параллельно с rewriter
    kw_triggers = redflag.detect_red_flags(question)

    try:
        client = get_openai()
        llm_flags_task = asyncio.create_task(redflag.detect_red_flags_llm(question, client))
        # 3. Query Rewriter
        legal_query = await rewriter.rewrite_query(question, client, profile.citizenship)

        # 4-5. Retrieval + Rerank (синхронные, CPU/сеть — уводим в поток)
        def _retrieve_and_rerank():
            from nomus.pipeline.reranker import rerank
            from nomus.pipeline.retriever import retrieve

            candidates = retrieve(legal_query, citizenship=profile.citizenship)
            return rerank(legal_query, candidates)

        top_chunks = await asyncio.to_thread(_retrieve_and_rerank)

        llm_triggers = await llm_flags_task
        triggers = kw_triggers + [t for t in llm_triggers if t not in kw_triggers]

        # 6.2 Abstention: ни один фрагмент не прошёл порог
        relevant = [c for c in top_chunks if c.score >= settings.relevance_threshold]
        if not relevant:
            return PipelineResult(
                kind="abstain",
                red_flag=bool(triggers),
                red_flag_triggers=triggers,
                abstain_reason="Я не нашёл точной нормы в законодательстве по вашему вопросу.",
                retrieved=top_chunks,
                latency_ms=_elapsed(),
            )

        # 6. Generate
        answer = await generate_answer(question, profile, relevant, client, triggers)

        # 6.2 Abstention: LLM вернул низкую уверенность
        if answer.confidence == "low":
            return PipelineResult(
                kind="abstain",
                red_flag=bool(triggers) or answer.red_flag,
                red_flag_triggers=triggers,
                abstain_reason="Я не уверен в точности нормы и не буду отвечать наугад.",
                retrieved=relevant,
                latency_ms=_elapsed(),
            )

        # 7. Validate: цитаты и обязательные поля
        ok, invalid = validate_citations(answer, relevant)
        if not ok:
            log.warning("Validator заблокировал ответ: невалидные цитаты %s", invalid)
            return PipelineResult(
                kind="abstain",
                red_flag=bool(triggers) or answer.red_flag,
                red_flag_triggers=triggers,
                abstain_reason="Не удалось подтвердить точность ссылок на статьи.",
                retrieved=relevant,
                latency_ms=_elapsed(),
            )
        if not validate_required_fields(answer):
            return PipelineResult(
                kind="abstain",
                red_flag=bool(triggers) or answer.red_flag,
                red_flag_triggers=triggers,
                abstain_reason="Я не нашёл точной нормы в законодательстве по вашему вопросу.",
                retrieved=relevant,
                latency_ms=_elapsed(),
            )

        if triggers:
            answer.red_flag = True

        return PipelineResult(
            kind="answer",
            answer=answer,
            red_flag=answer.red_flag,
            red_flag_triggers=triggers,
            retrieved=relevant,
            latency_ms=_elapsed(),
        )

    except Exception:
        log.exception("Pipeline error")
        # NFR-06: при отказе LLM/поиска — сообщение об ошибке + контакты, red-flag по ключевым словам
        return PipelineResult(
            kind="error",
            red_flag=bool(kw_triggers),
            red_flag_triggers=kw_triggers,
            latency_ms=_elapsed(),
        )
