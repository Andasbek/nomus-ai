"""Smoke-тесты без тяжёлых ML-зависимостей и внешних сервисов."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")


def test_imports():
    import nomus.bot.handlers  # noqa: F401
    import nomus.bot.main  # noqa: F401
    import nomus.ingest.parser  # noqa: F401
    import nomus.pipeline.orchestrator  # noqa: F401


def test_red_flag_detector():
    from nomus.pipeline.redflag import detect_red_flags

    assert detect_red_flags("мне не платят зарплату 3 месяца, паспорт забрал работодатель")
    assert detect_red_flags("паспорт отобрали и не выпускают с территории")
    assert "долговая кабала" in detect_red_flags("заставляют долг отрабатывать за билет")
    assert detect_red_flags("удерживают за жильё и еду из зарплаты")
    assert detect_red_flags("хочу узнать про отпуск") == []
    assert detect_red_flags("сколько часов можно работать в неделю?") == []


def test_citation_validator():
    from nomus.pipeline.validator import validate_citations
    from nomus.schemas import Answer, Chunk, RetrievedChunk, RightStatement

    chunks = [
        RetrievedChunk(
            chunk=Chunk(
                chunk_id="tk_rk_st_113_p2",
                text="…",
                doc_title="Трудовой кодекс РК",
                doc_short="ТК РК",
                article_num="113",
            ),
            score=0.9,
        )
    ]
    good = Answer(
        confidence="high",
        summary="s",
        rights=[RightStatement(statement="x", article="113", doc_short="ТК РК")],
    )
    ok, invalid = validate_citations(good, chunks)
    assert ok and not invalid

    bad = Answer(
        confidence="high",
        summary="s",
        rights=[RightStatement(statement="x", article="999", doc_short="ТК РК")],
    )
    ok, invalid = validate_citations(bad, chunks)
    assert not ok and invalid == ["ст. 999 ТК РК"]


def test_parser():
    from nomus.ingest.parser import DocMeta, parse_lines

    lines = [
        "Глава 10. Оплата труда",
        "Статья 113. Сроки и порядок выплаты заработной платы",
        "1. Заработная плата выплачивается в национальной валюте.",
        "2. Заработная плата выплачивается не реже одного раза в месяц.",
        "Статья 114. Утратила силу Законом РК от 01.01.2020.",
        "Утратила силу.",
        "Статья 115. Исчисление средней заработной платы",
        "Правила исчисления утверждаются уполномоченным органом.",
    ]
    meta = DocMeta(
        doc_title="Трудовой кодекс Республики Казахстан",
        doc_short="ТК РК",
        doc_id="K1500000414",
        revision_date="2026-01-15",
        url_base="https://adilet.zan.kz/rus/docs/K1500000414",
    )
    chunks = parse_lines(lines, meta)
    by_id = {c.chunk_id: c for c in chunks}

    assert "тк_рк_st_113_p1" in by_id and "тк_рк_st_113_p2" in by_id
    c = by_id["тк_рк_st_113_p2"]
    assert c.chapter == "Глава 10. Оплата труда"
    assert c.article_num == "113"
    assert "не реже одного раза в месяц" in c.text
    assert "национальной валюте" in c.parent_text  # parent = вся статья
    # DR-02: утратившая силу статья помечена
    assert all(ch.status == "excluded" for ch in chunks if ch.article_num == "114")
    assert any(ch.article_num == "115" and ch.status == "active" for ch in chunks)


def test_docgen():
    from nomus.docgen import ClaimFields, build_claim_docx, build_claim_text

    f = ClaimFields(
        full_name="Тестов Тест Тестович",
        citizenship="Узбекистан",
        employer="ТОО Ромашка",
        work_period="январь–март 2026",
        debt_amount="450 000",
        contact="+7 700 000 00 00",
        violated_articles=["ст. 113 ТК РК (сроки выплаты зарплаты)"],
    )
    text = build_claim_text(f)
    assert "ТОО Ромашка" in text and "ст. 113 ТК РК" in text and "450 000" in text

    data = build_claim_docx(f)
    assert data[:2] == b"PK" and len(data) > 1000  # валидный zip/docx


def test_db_roundtrip():
    from nomus import db

    db.init_db()
    db.upsert_session(42, citizenship_profile="EAEU", risk_profile="DOCUMENTED", disclaimer_ack=1)
    s = db.get_session(42)
    assert s["citizenship_profile"] == "EAEU" and s["disclaimer_ack"] == 1

    db.log_query(42, "секретный текст", ["c1"], "high", False, False, 1234)
    # приватность: сырой текст не хранится
    import sqlite3

    conn = sqlite3.connect(os.environ["DB_PATH"])
    rows = conn.execute("SELECT query_hash FROM queries WHERE user_id=42").fetchall()
    conn.close()
    assert rows and "секретный" not in rows[0][0]

    db.delete_user_data(42)
    assert db.get_session(42) is None


def test_profile_conservative_default():
    from nomus.schemas import RiskProfile, UserProfile

    p = UserProfile()
    assert p.effective_risk == RiskProfile.UNDOCUMENTED  # UNKNOWN → консервативно


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"[ok] {fn.__name__}")
    print(f"\n{len(fns)} тестов прошли успешно")
