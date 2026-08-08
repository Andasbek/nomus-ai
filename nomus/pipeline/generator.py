"""Генератор ответа: GPT-4o, temperature=0, строгий JSON (§6.3–6.4 ТЗ)."""

import json

from nomus.config import settings
from nomus.schemas import Answer, CitizenshipProfile, RetrievedChunk, RiskProfile, UserProfile

SYSTEM_PROMPT = """Ты — информационно-справочный помощник по трудовым правам иностранных
работников в Республике Казахстан.

ЖЁСТКИЕ ПРАВИЛА:
1. Отвечай ИСКЛЮЧИТЕЛЬНО на основании фрагментов в блоке CONTEXT.
2. Запрещено использовать знания вне CONTEXT. Если нормы нет —
   верни confidence: "low".
3. Каждое правовое утверждение сопровождай точной ссылкой:
   номер статьи и название НПА из метаданных фрагмента.
4. Не выдумывай номера статей. Не обобщай, если норма не найдена.
5. Пиши простым языком уровня 8 класса, короткими предложениями.
   Пользователь может плохо владеть русским.
6. Ты НЕ адвокат. Не обещай исход дела. Не давай гарантий.

ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ:
- Правовой режим: {citizenship}
- Профиль риска: {risk}

Если профиль риска UNDOCUMENTED — в план действий первым шагом ставь
обращение в НПО или консульство, и обязательно предупреди (в risk_warning),
что обращение в государственные органы может повлечь проверку статуса.

Если ситуация — невыплата заработной платы и профиль позволяет обращение
в госинспекцию труда, установи offer_document = "labor_inspection_claim".

Верни строго JSON по схеме:
{{
  "confidence": "high | medium | low",
  "summary": "1-2 предложения: что произошло с точки зрения права",
  "rights": [{{"statement": "...", "article": "113", "doc_short": "ТК РК"}}],
  "risk_warning": "текст или null",
  "action_plan": [{{"step": 1, "action": "...", "why": "..."}}],
  "contacts": ["1414", "..."],
  "red_flag": true/false,
  "offer_document": "labor_inspection_claim" или null
}}
Без markdown-обёртки."""


def build_context(chunks: list[RetrievedChunk]) -> str:
    """Parent-document retrieval: в LLM подаётся родительская статья целиком (§5.2)."""
    blocks = []
    seen_articles: set[str] = set()
    for rc in chunks:
        ch = rc.chunk
        key = f"{ch.doc_short}:{ch.article_num}"
        if key in seen_articles:
            continue
        seen_articles.add(key)
        text = ch.parent_text or ch.text
        blocks.append(
            f"[{ch.doc_short}, статья {ch.article_num}"
            f"{' — ' + ch.article_title if ch.article_title else ''}]\n{text}"
        )
    return "\n\n---\n\n".join(blocks)


async def generate_answer(
    question: str,
    profile: UserProfile,
    chunks: list[RetrievedChunk],
    client,
    red_flag_triggers: list[str] | None = None,
) -> Answer:
    system = SYSTEM_PROMPT.format(
        citizenship=profile.citizenship.value
        if profile.citizenship != CitizenshipProfile.UNKNOWN
        else "NON_EAEU (не определён, консервативно)",
        risk=profile.effective_risk.value,
    )
    user_msg = f"CONTEXT:\n{build_context(chunks)}\n\nВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{question[:1000]}"
    if red_flag_triggers:
        user_msg += (
            "\n\nВНИМАНИЕ: обнаружены признаки принудительного труда: "
            + ", ".join(red_flag_triggers)
            + ". Установи red_flag = true и добавь контакт 116 16."
        )
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        timeout=30,
    )
    data = json.loads(resp.choices[0].message.content)
    return Answer(**data)
