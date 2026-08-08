"""Обработчики бота: /start, FSM профилирования, вопросы, заявление, эскалация."""

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from nomus import db
from nomus.bot import keyboards as kb
from nomus.bot import render
from nomus.bot.states import ClaimForm, Consulting, Profiling
from nomus.contacts import render_contacts_md
from nomus.docgen import ClaimFields, build_claim_docx, build_claim_text
from nomus.pipeline.orchestrator import process_query
from nomus.schemas import CitizenshipProfile, RiskProfile, UserProfile

log = logging.getLogger(__name__)
router = Router()

EAEU_COUNTRIES = {"KG"}  # из кнопок MVP только Кыргызстан входит в ЕАЭС


def _profile_from_session(session: dict | None) -> UserProfile:
    if not session:
        return UserProfile()
    return UserProfile(
        citizenship=CitizenshipProfile(session.get("citizenship_profile") or "UNKNOWN"),
        risk=RiskProfile(session.get("risk_profile") or "UNKNOWN"),
    )


# ---------- /start и профилирование (FR-01..FR-04) ----------


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    db.upsert_session(message.from_user.id)
    session = db.get_session(message.from_user.id)
    if session and session["disclaimer_ack"] and session["citizenship_profile"] != "UNKNOWN":
        # FR-04: профиль уже собран — не спрашиваем повторно
        await state.set_state(Consulting.ready)
        await message.answer(
            "С возвращением! 👋 Опишите вашу ситуацию своими словами — я подскажу, "
            "что говорит закон.\n\nСбросить профиль: /reset",
            parse_mode="HTML",
        )
        return
    await state.set_state(Profiling.waiting_disclaimer)
    await message.answer(render.DISCLAIMER, reply_markup=kb.disclaimer_kb(), parse_mode="HTML")
    await message.answer(render.PRIVACY_NOTE, parse_mode="HTML")


@router.callback_query(F.data == "ack_disclaimer")
async def on_disclaimer_ack(cb: CallbackQuery, state: FSMContext) -> None:
    db.upsert_session(cb.from_user.id, disclaimer_ack=1)
    await state.set_state(Profiling.waiting_citizenship)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "🌍 <b>Гражданином какой страны вы являетесь?</b>\n"
        "<i>От этого зависят правила работы в Казахстане.</i>",
        reply_markup=kb.citizenship_kb(),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(F.data.startswith("cit:"))
async def on_citizenship(cb: CallbackQuery, state: FSMContext) -> None:
    code = cb.data.split(":", 1)[1]
    citizenship = "EAEU" if code in EAEU_COUNTRIES else "NON_EAEU"
    db.upsert_session(cb.from_user.id, citizenship_profile=citizenship)
    await state.update_data(citizenship_code=code)
    await state.set_state(Profiling.waiting_contract)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "📃 <b>У вас есть письменный трудовой договор с работодателем?</b>",
        reply_markup=kb.yes_no_kb("contract"),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(F.data.startswith("contract:"))
async def on_contract(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(has_contract=cb.data.split(":", 1)[1])
    await state.set_state(Profiling.waiting_registration)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(
        "🪪 <b>У вас есть действующая регистрация (и разрешение на работу, если требуется)?</b>",
        reply_markup=kb.yes_no_kb("reg"),
        parse_mode="HTML",
    )
    await cb.answer()


@router.callback_query(F.data.startswith("reg:"))
async def on_registration(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    has_contract = data.get("has_contract", "unknown")
    has_reg = cb.data.split(":", 1)[1]

    if has_contract == "yes" and has_reg == "yes":
        risk = "DOCUMENTED"
    elif "no" in (has_contract, has_reg):
        risk = "UNDOCUMENTED"
    else:
        risk = "UNKNOWN"  # трактуется консервативно, как UNDOCUMENTED

    db.upsert_session(cb.from_user.id, risk_profile=risk)
    await state.set_state(Consulting.ready)
    await cb.message.edit_reply_markup(reply_markup=None)

    note = ""
    if risk != "DOCUMENTED":
        note = (
            "\n\n⚠️ <i>Я буду учитывать, что ваши документы могут быть не в порядке, "
            "и подсказывать самые безопасные шаги.</i>"
        )
    await cb.message.answer(
        "✅ Спасибо! Теперь <b>опишите вашу ситуацию своими словами</b> — например: "
        "«не платят зарплату два месяца» или «хотят уволить без причины»." + note,
        parse_mode="HTML",
    )
    await cb.answer()


# ---------- Служебные команды ----------


@router.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext) -> None:
    db.reset_session(message.from_user.id)
    await state.clear()
    await message.answer("🔄 Профиль и история очищены. Нажмите /start, чтобы начать заново.")


@router.message(Command("delete"))
async def cmd_delete(message: Message, state: FSMContext) -> None:
    db.delete_user_data(message.from_user.id)
    await state.clear()
    await message.answer(
        "🗑 Все ваши данные удалены: профиль и служебные записи. "
        "Текст ваших обращений я и так не хранил. Нажмите /start, чтобы начать заново."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Я подсказываю трудовые права иностранных работников в Казахстане "
        "со ссылками на статьи законов.\n\n"
        "/start — начать\n/reset — сбросить профиль\n/delete — удалить мои данные",
    )


@router.callback_query(F.data == "need_lawyer")
async def on_need_lawyer(cb: CallbackQuery) -> None:
    await cb.message.answer(render_contacts_md(), parse_mode="HTML")
    await cb.answer()


# ---------- Заявление в госинспекцию труда (FR-30..FR-33) ----------

CLAIM_STEPS = [
    (ClaimForm.full_name, "full_name", "Введите ваши <b>ФИО полностью</b>:"),
    (ClaimForm.citizenship, "citizenship", "Ваше <b>гражданство</b>:"),
    (ClaimForm.employer, "employer", "Название <b>работодателя</b> (компания или ИП):"),
    (ClaimForm.work_period, "work_period", "Период работы (например: <i>январь–март 2026</i>):"),
    (ClaimForm.debt_amount, "debt_amount", "Сумма долга по зарплате, <b>в тенге</b>:"),
    (ClaimForm.contact, "contact", "Ваш <b>контакт</b> (телефон или адрес):"),
]


@router.callback_query(F.data == "make_claim")
async def on_make_claim(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CLAIM_STEPS[0][0])
    await cb.message.answer(
        "📄 Соберу заявление в государственную инспекцию труда. "
        "Задам 6 коротких вопросов.\n\n"
        "🔒 <i>Эти данные попадут только в файл заявления и не сохраняются.</i>",
        parse_mode="HTML",
    )
    await cb.message.answer(CLAIM_STEPS[0][2], parse_mode="HTML")
    await cb.answer()


def _register_claim_steps() -> None:
    for i, (st, field_name, _prompt) in enumerate(CLAIM_STEPS):
        next_prompt = CLAIM_STEPS[i + 1][2] if i + 1 < len(CLAIM_STEPS) else None
        next_state = CLAIM_STEPS[i + 1][0] if i + 1 < len(CLAIM_STEPS) else None

        def make_handler(field_name=field_name, next_prompt=next_prompt, next_state=next_state):
            async def handler(message: Message, state: FSMContext) -> None:
                await state.update_data(**{field_name: message.text.strip()})
                if next_state is not None:
                    await state.set_state(next_state)
                    await message.answer(next_prompt, parse_mode="HTML")
                else:
                    await _finish_claim(message, state)

            return handler

        router.message(st, F.text)(make_handler())


async def _finish_claim(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    fields = ClaimFields(
        full_name=data.get("full_name", ""),
        citizenship=data.get("citizenship", ""),
        employer=data.get("employer", ""),
        work_period=data.get("work_period", ""),
        debt_amount=data.get("debt_amount", ""),
        contact=data.get("contact", ""),
        violated_articles=data.get("violated_articles", []),
    )
    text = build_claim_text(fields)
    try:
        docx_bytes = build_claim_docx(fields)
        await message.answer_document(
            BufferedInputFile(docx_bytes, filename="zayavlenie_gosinspekcia_truda.docx"),
            caption="📄 Готово! Проверьте данные, распечатайте и подпишите.",
        )
    except Exception:
        log.exception("docx generation failed")
        # Fallback из §13 ТЗ: текст сообщением
        await message.answer(f"<pre>{text}</pre>", parse_mode="HTML")

    await message.answer(
        "Подать заявление можно в госинспекцию труда по месту нахождения работодателя "
        "или через портал eotinish.kz (нужна ЭЦП).\n\n"
        "🔒 Введённые данные удалены из памяти.",
    )
    # Приватность: чистим поля заявления, профиль не трогаем
    await state.set_state(Consulting.ready)
    await state.set_data({"violated_articles": data.get("violated_articles", [])})


_register_claim_steps()


# ---------- Основной поток вопросов (FR-10..FR-14, FR-20..FR-24) ----------


@router.message(F.text & ~F.text.startswith("/"))
async def on_question(message: Message, state: FSMContext) -> None:
    session = db.get_session(message.from_user.id)
    if not session or not session["disclaimer_ack"]:
        await cmd_start(message, state)
        return
    if session["citizenship_profile"] == "UNKNOWN":
        await state.set_state(Profiling.waiting_citizenship)
        await message.answer(
            "Сначала пара вопросов о вас 🙌",
            reply_markup=kb.citizenship_kb(),
        )
        return

    text = (message.text or "")[:1000]
    profile = _profile_from_session(session)

    await message.bot.send_chat_action(message.chat.id, "typing")
    result = await process_query(text, profile)

    db.log_query(
        user_id=message.from_user.id,
        query_text=text,
        retrieved_ids=[rc.chunk.chunk_id for rc in result.retrieved],
        confidence=result.answer.confidence if result.answer else "n/a",
        red_flag=result.red_flag,
        abstained=result.kind == "abstain",
        latency_ms=result.latency_ms,
    )

    # FR-23: red-flag — приоритетное сообщение ДО основного ответа
    if result.red_flag:
        await message.answer(
            render.render_red_flag_alert(result.red_flag_triggers), parse_mode="HTML"
        )

    if result.kind == "answer":
        # FR-33: запоминаем нарушенные статьи для шаблона заявления
        await state.update_data(
            violated_articles=[
                f"ст. {r.article} {r.doc_short} ({r.statement})" for r in result.answer.rights
            ]
        )
        await message.answer(
            render.render_answer(result, profile),
            reply_markup=kb.answer_kb(result.answer.offer_document),
            parse_mode="HTML",
        )
    elif result.kind == "abstain":
        await message.answer(
            render.render_abstention(result), reply_markup=kb.lawyer_kb(), parse_mode="HTML"
        )
    else:
        await message.answer(render.render_error(), parse_mode="HTML")
