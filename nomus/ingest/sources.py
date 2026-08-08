"""Реестр источников корпуса (§5.1 ТЗ).

Файлы кладутся в data/raw/ вручную или скачиваются скриптом download.py.
revision_date проверить на странице документа и обновить перед индексацией!
"""

from nomus.ingest.parser import DocMeta

SOURCES: list[dict] = [
    {
        "file": "tk_rk.html",
        "meta": DocMeta(
            doc_title="Трудовой кодекс Республики Казахстан",
            doc_short="ТК РК",
            doc_id="K1500000414",
            revision_date="2026-01-15",
            url_base="https://adilet.zan.kz/rus/docs/K1500000414",
        ),
        "download_url": "https://adilet.zan.kz/rus/docs/K1500000414",
        "priority": "M",
    },
    {
        "file": "migration_law.html",
        "meta": DocMeta(
            doc_title="Закон Республики Казахстан «О миграции населения»",
            doc_short="Закон о миграции",
            doc_id="Z1100000477",
            revision_date="2026-01-15",
            url_base="https://adilet.zan.kz/rus/docs/Z1100000477",
        ),
        "download_url": "https://adilet.zan.kz/rus/docs/Z1100000477",
        "priority": "M",
    },
    {
        "file": "koap_rk.html",
        "meta": DocMeta(
            doc_title="Кодекс РК об административных правонарушениях (главы: труд, миграция)",
            doc_short="КоАП РК",
            doc_id="K1400000235",
            revision_date="2026-01-15",
            url_base="https://adilet.zan.kz/rus/docs/K1400000235",
        ),
        "download_url": "https://adilet.zan.kz/rus/docs/K1400000235",
        "priority": "M",
        # §5.1 ТЗ: из КоАП — только выборочные статьи (труд, миграция).
        # Диапазоны по номерам статей (включительно):
        #   34 — ответственность иностранцев; 51 — административное выдворение;
        #   86–98 — нарушения трудового законодательства;
        #   516–521 — нарушения в области миграции, привлечение иностранной рабочей силы;
        #   693 — органы госконтроля в области трудового законодательства;
        #   916–917 — исполнение выдворения.
        "article_ranges": [(34, 34), (51, 51), (86, 98), (516, 521), (693, 693), (916, 917)],
    },
    {
        # Текст договора входит в страницу закона о ратификации на adilet.
        "file": "eaeu_treaty_full.html",
        "meta": DocMeta(
            doc_title="Договор о Евразийском экономическом союзе",
            doc_short="Договор о ЕАЭС",
            doc_id="Z1400000240",
            revision_date="2024-01-30",
            url_base="https://adilet.zan.kz/rus/docs/Z1400000240",
        ),
        "download_url": "https://adilet.zan.kz/rus/docs/Z1400000240",
        "priority": "M",
        # Раздел XXVI «Трудовая миграция»: ст. 96–98
        "article_ranges": [(96, 98)],
    },
]
