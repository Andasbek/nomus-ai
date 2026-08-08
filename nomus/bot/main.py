"""Точка входа бота: python -m nomus.bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from nomus import db
from nomus.bot.handlers import router
from nomus.config import settings


async def warmup() -> None:
    """Прогрев ML-моделей до приёма запросов (NFR-01, NFR-04).

    Без него первый пользователь ждёт ~15 секунд загрузки bge-m3.
    """
    log = logging.getLogger(__name__)

    def _load() -> None:
        from nomus.pipeline.reranker import rerank
        from nomus.pipeline.retriever import retrieve

        rerank("прогрев", retrieve("невыплата заработной платы", top_k=3))

    log.info("Прогреваю модели…")
    started = asyncio.get_running_loop().time()
    try:
        await asyncio.to_thread(_load)
        elapsed = asyncio.get_running_loop().time() - started
        log.info("Модели готовы за %.1f с", elapsed)
    except Exception:
        # Бот всё равно поднимется: пайплайн отдаст ошибку с контактами (NFR-06)
        log.exception("Прогрев не удался — продолжаю без него")


async def main() -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан. Скопируйте .env.example в .env и заполните.")

    db.init_db()
    await warmup()
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    logging.getLogger(__name__).info("Nomus AI bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
