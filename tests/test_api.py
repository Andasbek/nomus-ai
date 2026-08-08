"""Проверка веб-API на живом сервере: python tests/test_api.py [base_url]"""

import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    failures = 0
    with httpx.Client(base_url=BASE, timeout=120) as c:
        r = c.get("/api/health")
        failures += not check(
            "health", r.status_code == 200 and r.json()["status"] == "ok", r.json().get("bot_url", "")
        )

        r = c.get("/")
        failures += not check(
            "лендинг отдаётся", r.status_code == 200 and "Nomus AI" in r.text, f"{len(r.text)} байт"
        )
        failures += not check(
            "ссылка на бота в API", "t.me/" in c.get("/api/health").json()["bot_url"]
        )

        r = c.get("/api/contacts")
        d = r.json()
        failures += not check(
            "контакты", r.status_code == 200 and len(d["contacts"]) >= 5, f"{len(d['contacts'])} шт."
        )
        failures += not check(
            "горячая линия 116 16 в контактах",
            any("116 16" in x["value"] for x in d["contacts"]),
        )

        for f in ("/static/styles.css", "/static/app.js"):
            failures += not check(f"статика {f}", c.get(f).status_code == 200)

        # Сценарий 1: red-flag + safety-режим
        r = c.post(
            "/api/ask",
            json={
                "question": "Мне не платят зарплату 3 месяца, паспорт забрал работодатель",
                "citizenship": "NON_EAEU",
                "risk": "UNDOCUMENTED",
            },
        )
        d = r.json()
        failures += not check("ask: red-flag сценарий", r.status_code == 200, d.get("kind"))
        failures += not check("red_flag поднят", d.get("red_flag") is True, str(d.get("red_flag_triggers")))
        failures += not check(
            "предупреждение для UNDOCUMENTED", bool(d.get("risk_warning"))
        )
        if d["kind"] == "answer":
            arts = {x["article"] for x in d["rights"]}
            src = {s["article_num"] for s in d["sources"]}
            failures += not check(
                "цитаты подтверждены источниками", arts.issubset(src), f"{arts} ⊆ {src}"
            )
            failures += not check("ссылки на adilet в источниках",
                                  any("adilet" in s["url"] for s in d["sources"]))

        # Сценарий 2: развилка ЕАЭС
        q = "Нужно ли мне разрешение на работу в Казахстане?"
        eaeu = c.post("/api/ask", json={"question": q, "citizenship": "EAEU", "risk": "DOCUMENTED"}).json()
        non = c.post("/api/ask", json={"question": q, "citizenship": "NON_EAEU", "risk": "DOCUMENTED"}).json()
        failures += not check(
            "развилка ЕАЭС даёт разные ответы",
            eaeu.get("summary") != non.get("summary"),
            f"EAEU: {str(eaeu.get('summary'))[:60]}… | NON: {str(non.get('summary'))[:60]}…",
        )
        failures += not check(
            "для ЕАЭС найден Договор о ЕАЭС",
            any(s["doc_short"] == "Договор о ЕАЭС" for s in eaeu.get("sources", [])),
        )

        # Сценарий 3: abstention вне домена
        d = c.post(
            "/api/ask",
            json={"question": "Какая погода завтра в Алматы?", "citizenship": "NON_EAEU", "risk": "DOCUMENTED"},
        ).json()
        failures += not check("abstention вне домена", d["kind"] == "abstain", d.get("abstain_reason", ""))

        # Валидация входа
        r = c.post("/api/ask", json={"question": "аб", "citizenship": "EAEU", "risk": "DOCUMENTED"})
        failures += not check("короткий вопрос отклонён", r.status_code == 422)

        # Генерация .docx
        r = c.post(
            "/api/claim",
            json={
                "full_name": "Тестов Тест",
                "citizenship": "Узбекистан",
                "employer": "ТОО Ромашка",
                "work_period": "январь–март 2026",
                "debt_amount": "450000",
                "contact": "+7 700 000 00 00",
                "violated_articles": ["ст. 113 ТК РК"],
            },
        )
        failures += not check(
            "заявление .docx", r.status_code == 200 and r.content[:2] == b"PK", f"{len(r.content)} байт"
        )

    print(f"\n{'ВСЁ ПРОШЛО' if not failures else str(failures) + ' ПРОВЕРОК УПАЛО'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
