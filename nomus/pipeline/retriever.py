"""Гибридный retrieval в Qdrant: dense + sparse, RRF-объединение, фильтр status=active
(FR-12, §6.1 п.4 ТЗ)."""

from qdrant_client import QdrantClient, models

from nomus.config import settings
from nomus.pipeline.embeddings import embed
from nomus.schemas import Chunk, CitizenshipProfile, RetrievedChunk

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url)
    return _client


EAEU_DOC = "Договор о ЕАЭС"
# Гарантированная квота для малых, но решающих документов: корпус Договора о ЕАЭС
# — 33 чанка против 2200+ остальных, поэтому в общем пуле он тонет.
EAEU_QUOTA = 5


def _search(query: str, top_k: int, doc_short: str | None = None) -> list[RetrievedChunk]:
    dense, sparse = embed([query])
    sparse_vec = models.SparseVector(
        indices=list(sparse[0].keys()), values=list(sparse[0].values())
    )
    conditions = [models.FieldCondition(key="status", match=models.MatchValue(value="active"))]
    if doc_short:
        conditions.append(
            models.FieldCondition(key="doc_short", match=models.MatchValue(value=doc_short))
        )
    flt = models.Filter(must=conditions)
    result = get_client().query_points(
        collection_name=settings.qdrant_collection,
        prefetch=[
            models.Prefetch(query=dense[0], using="dense", limit=top_k * 2, filter=flt),
            models.Prefetch(query=sparse_vec, using="sparse", limit=top_k * 2, filter=flt),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
        with_payload=True,
    )
    return [RetrievedChunk(chunk=Chunk(**p.payload), score=float(p.score)) for p in result.points]


def retrieve(
    query: str, top_k: int | None = None, citizenship: CitizenshipProfile | None = None
) -> list[RetrievedChunk]:
    """Гибридный поиск. Для граждан ЕАЭС досыпает чанки Договора о ЕАЭС.

    Итоговую релевантность всё равно решает reranker — квота лишь гарантирует,
    что профильная норма вообще дойдёт до него (§11 ТЗ: ветвление в фильтрах).
    """
    top_k = top_k or settings.retrieval_top_k
    candidates = _search(query, top_k)

    if citizenship == CitizenshipProfile.EAEU:
        found = {c.chunk.chunk_id for c in candidates}
        for rc in _search(query, EAEU_QUOTA, doc_short=EAEU_DOC):
            if rc.chunk.chunk_id not in found:
                candidates.append(rc)
                found.add(rc.chunk.chunk_id)
    return candidates
