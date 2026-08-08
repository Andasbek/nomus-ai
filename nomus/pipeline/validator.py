"""Validator цитат (FR-21, §6.1 п.7): каждая статья из ответа обязана присутствовать
в извлечённом контексте. Иначе — блокировка ответа (abstention)."""

from nomus.schemas import Answer, RetrievedChunk


def _norm(s: str) -> str:
    return s.strip().lower().replace("ст.", "").replace("статья", "").strip()


def validate_citations(answer: Answer, chunks: list[RetrievedChunk]) -> tuple[bool, list[str]]:
    """Возвращает (ok, список_невалидных_цитат)."""
    available: set[tuple[str, str]] = set()
    for rc in chunks:
        available.add((_norm(rc.chunk.doc_short), _norm(rc.chunk.article_num)))

    invalid: list[str] = []
    for right in answer.rights:
        key = (_norm(right.doc_short), _norm(right.article))
        if key not in available:
            invalid.append(f"ст. {right.article} {right.doc_short}")
    return (len(invalid) == 0, invalid)


def validate_required_fields(answer: Answer) -> bool:
    """Обязательные поля содержательного ответа: summary + хотя бы одно право или план."""
    if not answer.summary.strip():
        return False
    if not answer.rights and not answer.action_plan:
        return False
    return True
