"""Обёртка над bge-m3: dense + sparse эмбеддинги. Ленивая загрузка модели."""

from functools import lru_cache


@lru_cache(maxsize=1)
def get_model():
    from FlagEmbedding import BGEM3FlagModel

    from nomus.config import settings
    from nomus.pipeline.device import get_device, use_fp16

    return BGEM3FlagModel(settings.embedding_model, use_fp16=use_fp16(), devices=get_device())


def embed(texts: list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
    """Возвращает (dense_векторы, sparse_векторы {token_id: weight})."""
    model = get_model()
    out = model.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
        max_length=8192,
    )
    dense = [v.tolist() for v in out["dense_vecs"]]
    sparse = [{int(k): float(v) for k, v in w.items()} for w in out["lexical_weights"]]
    return dense, sparse
