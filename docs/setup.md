# Установка и запуск

## Требования

| Компонент | Версия | Примечание |
|---|---|---|
| Python | 3.11 | на 3.12+ не проверялось |
| Docker | любой актуальный | для Qdrant |
| Оперативная память | от 8 ГБ | модели bge-m3 и reranker |
| Диск | ~6 ГБ | веса моделей в кэше HuggingFace |
| GPU NVIDIA | опционально | ускоряет reranker в десятки раз |

Нужны два внешних ключа: токен Telegram-бота от [@BotFather](https://t.me/BotFather)
и ключ OpenAI API.

## Шаг 1. Зависимости

```bash
pip install -r requirements.txt
```

Пакеты `torch` и `FlagEmbedding` весят несколько гигабайт — это нормально.
Если планируется работа на GPU, устанавливать torch нужно иначе, см. раздел
«GPU» ниже.

## Шаг 2. Переменные окружения

```bash
cp .env.example .env
```

Заполните минимум два поля:

```bash
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
```

Полный список переменных с пояснениями — в конце этой страницы.

> Файл `.env` защищён `.gitignore` и не попадает в репозиторий. Не переносите
> ключи в другие файлы и не передавайте их в аргументах командной строки.

## Шаг 3. Qdrant

```bash
docker compose up -d qdrant
curl http://localhost:6333/healthz     # ожидается: healthz check passed
```

Данные хранятся в каталоге `./.qdrant`, поэтому индекс переживает перезапуск
контейнера.

## Шаг 4. Корпус законов

```bash
python -m nomus.ingest.download    # скачать НПА с adilet.zan.kz
python -m nomus.ingest             # распарсить и проиндексировать
```

Ожидаемый результат:

```
[parse] tk_rk.html: 1667 чанков, из них active: 1652
[parse] migration_law.html: 644 чанков, из них active: 605
[parse] koap_rk.html: 141 чанков, из них active: 130
[parse] eaeu_treaty_full.html: 33 чанков, из них active: 33
[dedup] удалено дубликатов: 603
[dump] data/chunks/chunks.json: 1817 чанков
[done] коллекция nomus_kz_legal_v1: 1817 точек
```

Первый запуск дополнительно скачивает модель bge-m3 (~2 ГБ). Индексация на CPU
занимает 20–40 минут, на GPU — заметно быстрее.

Если скачивание не удалось из-за TLS-ошибки, см.
[Решение проблем](troubleshooting.md#не-скачиваются-нпа-с-adiletzankz).

Подробности о структуре корпуса — в [Корпус НПА](corpus.md).

## Шаг 5. Запуск

```bash
python -m nomus.bot.main    # Telegram-бот
python -m nomus.api.main    # сайт и API на http://localhost:8000
```

Оба процесса независимы: можно запустить только один. Перед приёмом запросов
каждый прогревает модели — дождитесь строк `Модели готовы` и
`Application startup complete`, иначе первый пользователь будет ждать около
40 секунд.

## Всё сразу через Docker

```bash
docker compose up
```

Поднимает Qdrant, бота и веб-сервис. Корпус всё равно нужно проиндексировать
один раз — команду `python -m nomus.ingest` выполните на хосте либо внутри
контейнера. Кэш моделей вынесен в том `hf_cache`, поэтому пересборка образа не
приводит к повторной загрузке весов.

## GPU

Reranker — самое тяжёлое место пайплайна, и на GPU он работает в десятки раз
быстрее (0,15 с против нескольких секунд). ТЗ отдельно отмечало это как риск
для требования по времени ответа.

Проверка наличия карты:

```bash
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

Если вторая команда печатает `False` при наличии карты, установлена CPU-сборка
torch. Заменить её так:

```bash
# подобрать индекс под свою версию CUDA
pip index versions torch --index-url https://download.pytorch.org/whl/cu130
pip install --index-url https://download.pytorch.org/whl/cu130 "torch==2.13.0+cu130"
```

Важная деталь: если версия совпадает с уже установленной, `pip` посчитает
требование выполненным и **не** заменит сборку. Поэтому версия указывается явно
с суффиксом `+cu130`. Подробный разбор — в
[Решение проблем](troubleshooting.md#torch-не-видит-gpu).

Выбирать устройство в коде не нужно: [device.py](../nomus/pipeline/device.py)
определяет его сам и включает fp16 только на CUDA — на CPU режим fp16
эмулируется и лишь замедляет вычисления.

## Проверка работоспособности

```bash
python tests/test_smoke.py              # без сети и тяжёлых моделей
python tests/test_api.py                # против запущенного API
python tests/test_api.py https://ваш-домен
```

`test_smoke.py` проверяет парсер, валидатор цитат, red-flag детектор, генерацию
`.docx`, работу с базой и консервативную трактовку неизвестного профиля.

`test_api.py` делает живые запросы: red-flag сценарий, развилка ЕАЭС, отказ вне
домена, скачивание документа. Он тратит запросы к OpenAI.

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен бота, обязателен для бота |
| `OPENAI_API_KEY` | — | ключ OpenAI, обязателен |
| `OPENAI_MODEL` | `gpt-4o` | модель генерации |
| `QDRANT_URL` | `http://localhost:6333` | адрес векторной базы |
| `QDRANT_COLLECTION` | `nomus_kz_legal_v1` | имя коллекции |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | модель эмбеддингов |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | cross-encoder |
| `RETRIEVAL_TOP_K` | `20` | кандидатов из поиска |
| `RERANK_TOP_K` | `5` | фрагментов в модель |
| `RELEVANCE_THRESHOLD` | `0.35` | ниже порога — отказ от ответа |
| `DB_PATH` | `./data/nomus.db` | файл SQLite |
| `LOG_LEVEL` | `INFO` | уровень логирования |
| `BOT_USERNAME` | `nomus_law_bot` | подставляется в ссылки на сайте |
| `API_HOST` | `0.0.0.0` | интерфейс веб-сервиса |
| `API_PORT` | `8000` | порт веб-сервиса |
| `CORS_ORIGINS` | `*` | разрешённые источники запросов |
| `RATE_LIMIT_PER_HOUR` | `30` | лимит запросов с одного IP |
| `TRUSTED_PROXY` | `false` | читать `CF-Connecting-IP` за прокси |

`TRUSTED_PROXY` включайте **только** при работе за обратным прокси. При прямом
доступе к сервису это позволило бы обойти лимит подделкой заголовка — см.
[Развёртывание](deployment.md).
