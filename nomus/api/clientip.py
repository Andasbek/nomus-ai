"""Определение реального IP клиента за обратным прокси (cloudflared, nginx).

Без этого за туннелем все посетители выглядят как 127.0.0.1 и делят один
счётчик rate limit на всех.

Доверять заголовкам можно только тогда, когда мы действительно стоим за прокси:
иначе любой клиент подделает X-Forwarded-For и обойдёт лимит. Поэтому режим
включается явно — переменной TRUSTED_PROXY.
"""

from fastapi import Request

from nomus.config import settings


def client_ip(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    if not settings.trusted_proxy:
        return direct

    # Cloudflare кладёт исходный адрес сюда и перезаписывает его сам,
    # поэтому заголовок надёжнее X-Forwarded-For.
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()

    xff = request.headers.get("x-forwarded-for")
    if xff:
        # Первый элемент — исходный клиент, остальные дописали прокси по пути.
        return xff.split(",")[0].strip()

    real = request.headers.get("x-real-ip")
    return real.strip() if real else direct
