"""Reranker bge-reranker-v2-m3: top-20 → top-5 с порогом релевантности (FR-12, §6.1 п.5).

Cross-encoder используется напрямую через transformers, а не через обёртку
FlagEmbedding: та вызывает `tokenizer.prepare_for_model`, которого нет в
transformers 5.x.
"""

from functools import lru_cache

from nomus.config import settings
from nomus.schemas import RetrievedChunk

MAX_LENGTH = 512
BATCH_SIZE = 16


@lru_cache(maxsize=1)
def get_reranker():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    from nomus.pipeline.device import get_device, use_fp16

    device = get_device()
    tokenizer = AutoTokenizer.from_pretrained(settings.reranker_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        settings.reranker_model,
        dtype=torch.float16 if use_fp16() else torch.float32,
    )
    model.to(device)
    model.eval()
    return tokenizer, model, device


def compute_scores(query: str, texts: list[str]) -> list[float]:
    """Возвращает релевантность в диапазоне 0..1 (сигмоида от логита)."""
    import torch

    tokenizer, model, device = get_reranker()
    scores: list[float] = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            inputs = tokenizer(
                [query] * len(batch),
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            ).to(device)
            logits = model(**inputs).logits.view(-1).float()
            scores.extend(torch.sigmoid(logits).cpu().tolist())
    return scores


def rerank(
    query: str, candidates: list[RetrievedChunk], top_k: int | None = None
) -> list[RetrievedChunk]:
    """Возвращает top-k кандидатов с нормализованным скором; порог применяет orchestrator."""
    if not candidates:
        return []
    top_k = top_k or settings.rerank_top_k
    scores = compute_scores(query, [c.chunk.text for c in candidates])
    rescored = [
        RetrievedChunk(chunk=c.chunk, score=float(s)) for c, s in zip(candidates, scores)
    ]
    rescored.sort(key=lambda r: r.score, reverse=True)
    return rescored[:top_k]
