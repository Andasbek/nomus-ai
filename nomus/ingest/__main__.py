"""Индексация корпуса одной командой: python -m nomus.ingest  (DR-04).

Шаги: парсинг data/raw/ → чанки (JSON-дамп в data/chunks/) → эмбеддинги
bge-m3 (dense+sparse) → загрузка в Qdrant с фильтруемыми метаданными.
"""

import json
import re
from pathlib import Path

from qdrant_client import QdrantClient, models

from nomus.config import settings
from nomus.ingest.parser import parse_html_file, parse_text_file
from nomus.ingest.sources import SOURCES
from nomus.schemas import Chunk

RAW_DIR = Path("data/raw")
CHUNKS_DIR = Path("data/chunks")
BATCH = 32


def parse_all() -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for src in SOURCES:
        path = RAW_DIR / src["file"]
        if not path.exists():
            print(f"[warn] нет файла {path} — пропускаю ({src['meta'].doc_title})")
            continue
        if path.suffix == ".html":
            chunks = parse_html_file(str(path), src["meta"])
        else:
            chunks = parse_text_file(str(path), src["meta"])
        ranges = src.get("article_ranges")
        if ranges:
            chunks = [c for c in chunks if _in_ranges(c.article_num, ranges)]
        active = [c for c in chunks if c.status == "active"]
        print(f"[parse] {path.name}: {len(chunks)} чанков, из них active: {len(active)}")
        all_chunks.extend(active)  # DR-02: неактуальные не индексируем

    # Дедупликация: на некоторых страницах adilet текст встречается дважды
    seen: set[str] = set()
    unique = [c for c in all_chunks if not (c.chunk_id in seen or seen.add(c.chunk_id))]
    if len(unique) < len(all_chunks):
        print(f"[dedup] удалено дубликатов: {len(all_chunks) - len(unique)}")
    return unique


def _in_ranges(article_num: str, ranges: list[tuple[int, int]]) -> bool:
    m = re.match(r"(\d+)", article_num)
    if not m:
        return False
    n = int(m.group(1))
    return any(lo <= n <= hi for lo, hi in ranges)


def dump_chunks(chunks: list[Chunk]) -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    out = CHUNKS_DIR / "chunks.json"
    out.write_text(
        json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"[dump] {out}: {len(chunks)} чанков")


def ensure_collection(client: QdrantClient, dense_dim: int) -> None:
    if client.collection_exists(settings.qdrant_collection):
        client.delete_collection(settings.qdrant_collection)
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            "dense": models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )
    client.create_payload_index(
        settings.qdrant_collection, "status", models.PayloadSchemaType.KEYWORD
    )
    client.create_payload_index(
        settings.qdrant_collection, "doc_short", models.PayloadSchemaType.KEYWORD
    )


def index(chunks: list[Chunk]) -> None:
    from nomus.pipeline.embeddings import embed

    client = QdrantClient(url=settings.qdrant_url)
    print(f"[embed] считаю эмбеддинги для {len(chunks)} чанков (bge-m3)…")

    first_batch = True
    point_id = 0
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i : i + BATCH]
        dense, sparse = embed([c.text for c in batch])
        if first_batch:
            ensure_collection(client, dense_dim=len(dense[0]))
            first_batch = False
        points = []
        for c, dv, sv in zip(batch, dense, sparse):
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "dense": dv,
                        "sparse": models.SparseVector(
                            indices=list(sv.keys()), values=list(sv.values())
                        ),
                    },
                    payload=c.model_dump(),
                )
            )
            point_id += 1
        client.upsert(settings.qdrant_collection, points)
        print(f"[index] {min(i + BATCH, len(chunks))}/{len(chunks)}")

    info = client.get_collection(settings.qdrant_collection)
    print(f"[done] коллекция {settings.qdrant_collection}: {info.points_count} точек")


def main() -> None:
    chunks = parse_all()
    if not chunks:
        raise SystemExit(
            "Нет чанков. Положите исходники в data/raw/ "
            "(python -m nomus.ingest.download или вручную)."
        )
    n = len(chunks)
    if not (1000 <= n <= 5000):
        print(f"[note] размер корпуса {n} чанков (цель MVP: 1500–3000, DR-05)")
    dump_chunks(chunks)
    index(chunks)


if __name__ == "__main__":
    main()
