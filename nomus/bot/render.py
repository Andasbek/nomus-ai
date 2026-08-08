"""Рендер результата пайплайна в сообщения Telegram (FR-14, §6.1 п.8)."""

from html import escape

from nomus.contacts import RED_FLAG_HOTLINE, SAFE_FIRST_CONTACTS
from nomus.schemas import PipelineResult, RiskProfile, UserProfile

DISCLAIMER = (
    "ℹ️ Это информационно-справочный сервис. Вы общаетесь с искусственным интеллектом. "
    "Я предоставляю правовую информацию со ссылками на законы РК, но "
    "<b>не оказываю юридическую консультацию</b> и не заменяю адвоката. "
    "Для решения вашего дела обратитесь к юристу или в организацию помощи мигрантам."
)

DISCLAIMER_FOOTER = (
    "\n\n<i>ℹ️ Это правовая информация, а не юридическая консультация. "
    "Для решения вашего дела обратитесь к юристу.</i>"
)

PRIVACY_NOTE = (
    "🔒 Переписка в Telegram не даёт абсолютной анонимности. "
    "Я не сохраняю текст ваших обращений и персональные данные. "
    "Команда /delete удалит все ваши данные."
)


def render_red_flag_alert(triggers: list[str]) -> str:
    t = ", ".join(escape(x) for x in triggers) if triggers else "признаки принудительного труда"
    return (
        "🚨 <b>Важно! В вашей ситуации есть признаки принудительного труда</b>"
        f" ({t}).\n\n"
        f"📞 Позвоните на горячую линию <b>{RED_FLAG_HOTLINE}</b> — "
        "национальная линия по борьбе с торговлей людьми. "
        "Круглосуточно, бесплатно, анонимно.\n\n"
        "Также можно обратиться в НПО «Sana Sezim» или консульство вашей страны."
    )


def render_answer(result: PipelineResult, profile: UserProfile) -> str:
    a = result.answer
    parts: list[str] = []

    parts.append(f"📌 <b>Суть ситуации</b>\n{escape(a.summary)}")

    if a.rights:
        rights_lines = [
            f"• {escape(r.statement)}\n  <i>— ст. {escape(r.article)} {escape(r.doc_short)}</i>"
            for r in a.rights
        ]
        parts.append("⚖️ <b>Ваши права</b>\n" + "\n".join(rights_lines))

    if a.risk_warning:
        parts.append(f"⚠️ <b>Предупреждение</b>\n{escape(a.risk_warning)}")
    elif profile.effective_risk == RiskProfile.UNDOCUMENTED:
        # FR-24: страховка, если LLM не вернул предупреждение
        parts.append(
            "⚠️ <b>Предупреждение</b>\nУ вас нет подтверждённых документов. "
            "Обращение в государственные органы может повлечь проверку вашего статуса. "
            "Сначала посоветуйтесь с НПО или консульством:\n"
            + "\n".join(f"• {c}" for c in SAFE_FIRST_CONTACTS)
        )

    if a.action_plan:
        steps = []
        for s in sorted(a.action_plan, key=lambda x: x.step):
            line = f"{s.step}. {escape(s.action)}"
            if s.why:
                line += f"\n   <i>({escape(s.why)})</i>"
            steps.append(line)
        parts.append("🧭 <b>План действий</b>\n" + "\n".join(steps))

    if a.contacts:
        parts.append("📞 <b>Куда обратиться</b>\n" + "\n".join(f"• {escape(c)}" for c in a.contacts))

    return "\n\n".join(parts) + DISCLAIMER_FOOTER


def render_abstention(result: PipelineResult) -> str:
    reason = result.abstain_reason or "Я не нашёл точной нормы в законодательстве."
    return (
        f"🤷 <b>{escape(reason)}</b>\n\n"
        "Я отвечаю только тогда, когда могу подтвердить ответ конкретной статьёй закона. "
        "Отвечать наугад в правовых вопросах опасно.\n\n"
        "Рекомендую обратиться к живым специалистам — нажмите кнопку ниже."
    )


def render_error() -> str:
    return (
        "😔 <b>Сервис временно недоступен.</b>\n\n"
        "Попробуйте ещё раз через пару минут. Если вопрос срочный:\n"
        "• <b>1414</b> — единый контакт-центр (24/7, бесплатно)\n"
        "• <b>116 16</b> — горячая линия по борьбе с торговлей людьми"
    )
