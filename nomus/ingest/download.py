"""Скачивание исходников с adilet.zan.kz: python -m nomus.ingest.download

Fallback из §13 ТЗ: если сайт недоступен/блокирует — сохранить страницы
вручную (Ctrl+S в браузере) в data/raw/ под именами из sources.py.
"""

from pathlib import Path

import httpx

from nomus.ingest.sources import SOURCES

RAW_DIR = Path("data/raw")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
}


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for src in SOURCES:
        target = RAW_DIR / src["file"]
        if target.exists():
            print(f"[skip] {target} уже существует")
            continue
        url = src.get("download_url")
        if not url:
            print(f"[manual] {target}: сохраните вручную ({src['meta'].doc_title})")
            continue
        print(f"[get] {url} -> {target}")
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            target.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            # Частый случай: certifi не знает промежуточный сертификат adilet.
            # curl на Windows проверяет TLS через системное хранилище и обычно проходит.
            print(
                f"[fail] {url}: {e}\n"
                f"       Попробуйте: curl.exe -sSL -A \"Mozilla/5.0\" -o {target} {url}\n"
                f"       или сохраните страницу вручную в {target}"
            )


if __name__ == "__main__":
    main()
