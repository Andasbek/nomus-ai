"""FSM-состояния диалога."""

from aiogram.fsm.state import State, StatesGroup


class Profiling(StatesGroup):
    waiting_disclaimer = State()
    waiting_citizenship = State()
    waiting_contract = State()
    waiting_registration = State()


class Consulting(StatesGroup):
    ready = State()  # профиль собран, ждём вопрос


class ClaimForm(StatesGroup):
    """Сбор полей заявления (FR-31). Данные живут только в FSM-памяти."""

    full_name = State()
    citizenship = State()
    employer = State()
    work_period = State()
    debt_amount = State()
    contact = State()
