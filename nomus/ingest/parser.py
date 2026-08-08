"""Парсер НПА (§5, DR-01): HTML/текст с adilet.zan.kz → иерархия
Кодекс → Глава → Статья → Пункт → чанки по схеме §5.2.

Чанкинг по структуре документа, не по токенам. Минимальная единица — пункт
статьи; parent_text — статья целиком (parent-document retrieval).
"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from nomus.schemas import Chunk

ARTICLE_RE = re.compile(r"^Статья\s+(\d+[\-–]?\d*)\.?\s*(.*)$")
CHAPTER_RE = re.compile(r"^(Глава|ГЛАВА|РАЗДЕЛ|Раздел|Параграф)\s+(\d+[\-–]?\d*)\.?\s*(.*)$")
POINT_RE = re.compile(r"^(\d+(?:-\d+)?)[\.\)]\s+(.+)$")


@dataclass
class DocMeta:
    doc_title: str
    doc_short: str
    doc_id: str
    revision_date: str
    url_base: str
    lang: str = "ru"


def html_to_lines(html: str) -> list[str]:
    """Извлекает текстовые строки из HTML adilet (или любого сохранённого HTML)."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    return [ln for ln in lines if ln]


def parse_lines(lines: list[str], meta: DocMeta) -> list[Chunk]:
    """Разбирает плоский список строк в чанки-пункты статей."""
    chunks: list[Chunk] = []
    chapter = ""
    article_num = ""
    article_title = ""
    article_lines: list[str] = []

    def flush_article() -> None:
        nonlocal article_lines
        if not article_num or not article_lines:
            article_lines = []
            return
        parent_text = "\n".join(article_lines).strip()
        excluded = _is_excluded(parent_text)
        points = _split_points(article_lines)
        slug = meta.doc_short.lower().replace(" ", "_").replace(".", "")
        for point_num, point_text in points:
            suffix = f"_p{point_num}" if point_num else ""
            chunks.append(
                Chunk(
                    chunk_id=f"{slug}_st_{article_num}{suffix}",
                    text=point_text,
                    parent_text=parent_text,
                    doc_title=meta.doc_title,
                    doc_short=meta.doc_short,
                    doc_id=meta.doc_id,
                    chapter=chapter,
                    article_num=article_num,
                    article_title=article_title,
                    point_num=point_num,
                    revision_date=meta.revision_date,
                    status="excluded" if excluded else "active",
                    url=f"{meta.url_base}#z{article_num}",
                    lang=meta.lang,
                )
            )
        article_lines = []

    for line in lines:
        m = CHAPTER_RE.match(line)
        if m:
            flush_article()
            chapter = line
            continue
        m = ARTICLE_RE.match(line)
        if m:
            flush_article()
            article_num = m.group(1)
            article_title = m.group(2).strip()
            article_lines = []
            continue
        if article_num:
            article_lines.append(line)

    flush_article()
    return chunks


def _split_points(lines: list[str]) -> list[tuple[str, str]]:
    """Делит текст статьи на пункты. Если пунктов нет — одна запись с point_num=''. """
    points: list[tuple[str, list[str]]] = []
    current_num = ""
    current: list[str] = []
    for line in lines:
        m = POINT_RE.match(line)
        if m:
            if current:
                points.append((current_num, current))
            current_num = m.group(1)
            current = [line]
        else:
            current.append(line)
    if current:
        points.append((current_num, current))
    return [(num, "\n".join(ls).strip()) for num, ls in points if ls]


EXCLUDED_MARKERS = (
    "утратил силу",
    "утратила силу",
    "исключен ",
    "исключена ",
    "исключен.",
    "исключена.",
)


def _is_excluded(text: str) -> bool:
    """DR-02: статьи, утратившие силу, помечаются и исключаются из индекса."""
    head = text[:200].lower()
    return any(m in head for m in EXCLUDED_MARKERS)


def parse_html_file(path: str, meta: DocMeta) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        html = f.read()
    return parse_lines(html_to_lines(html), meta)


def parse_text_file(path: str, meta: DocMeta) -> list[Chunk]:
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.read().split("\n")]
    return parse_lines([ln for ln in lines if ln], meta)
