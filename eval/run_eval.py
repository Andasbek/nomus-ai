"""Прогон тестового датасета через пайплайн + метрики RAGAS (§10 ТЗ).

Запуск:  python -m eval.run_eval            — прогон пайплайна, свои метрики
         python -m eval.run_eval --ragas    — дополнительно RAGAS (нужен OPENAI_API_KEY)

Свои метрики (считаются без RAGAS):
- Citation Accuracy — доля ответов без выдуманных статей (блокирующий критерий = 1.00)
- Abstention Rate (вне домена) — цель >= 0.90
- Red-flag Recall — доля кейсов, где red-flag сработал, когда должен был
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nomus.pipeline.orchestrator import process_query  # noqa: E402
from nomus.pipeline.validator import validate_citations  # noqa: E402
from nomus.schemas import CitizenshipProfile, RiskProfile, UserProfile  # noqa: E402

DATASET = Path(__file__).parent / "dataset.json"
RESULTS = Path(__file__).parent / "results.json"


async def run_case(case: dict) -> dict:
    profile = UserProfile(
        citizenship=CitizenshipProfile(case["profile"]["citizenship"]),
        risk=RiskProfile(case["profile"]["risk"]),
    )
    result = await process_query(case["question"], profile)
    citations_ok = True
    answer_text = ""
    cited = []
    if result.answer:
        citations_ok, _ = validate_citations(result.answer, result.retrieved)
        cited = [r.article for r in result.answer.rights]
        answer_text = json.dumps(result.answer.model_dump(), ensure_ascii=False)
    return {
        "id": case["id"],
        "question": case["question"],
        "kind": result.kind,
        "abstained": result.kind == "abstain",
        "red_flag": result.red_flag,
        "cited_articles": cited,
        "citations_ok": citations_ok,
        "latency_ms": result.latency_ms,
        "answer": answer_text,
        "contexts": [rc.chunk.parent_text or rc.chunk.text for rc in result.retrieved],
        "ground_truth": case["ground_truth"],
        "expects_red_flag": case["expects_red_flag"],
        "expects_abstention": case["expects_abstention"],
    }


def summarize(rows: list[dict]) -> None:
    answered = [r for r in rows if r["kind"] == "answer"]
    out_of_domain = [r for r in rows if r["expects_abstention"]]
    red_cases = [r for r in rows if r["expects_red_flag"]]

    citation_acc = (
        sum(1 for r in answered if r["citations_ok"]) / len(answered) if answered else 1.0
    )
    abstention_rate = (
        sum(1 for r in out_of_domain if r["abstained"]) / len(out_of_domain)
        if out_of_domain
        else 1.0
    )
    red_recall = (
        sum(1 for r in red_cases if r["red_flag"]) / len(red_cases) if red_cases else 1.0
    )
    p95 = sorted(r["latency_ms"] for r in rows)[int(len(rows) * 0.95) - 1] if rows else 0

    print("\n===== МЕТРИКИ =====")
    print(f"Citation Accuracy (цель = 1.00):        {citation_acc:.2f}")
    print(f"Abstention Rate вне домена (>= 0.90):   {abstention_rate:.2f}")
    print(f"Red-flag Recall:                        {red_recall:.2f}")
    print(f"Latency p95 (<= 12000 мс):              {p95} мс")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ragas", action="store_true", help="также посчитать RAGAS")
    args = parser.parse_args()

    cases = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        print(f"[run] {case['id']}: {case['question'][:60]}…")
        rows.append(await run_case(case))

    RESULTS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[save] {RESULTS}")
    summarize(rows)

    if args.ragas:
        run_ragas(rows)


def run_ragas(rows: list[dict]) -> None:
    """RAGAS: faithfulness, answer_relevancy, context_precision/recall (§10.2)."""
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    answered = [r for r in rows if r["kind"] == "answer" and r["contexts"]]
    if not answered:
        print("[ragas] нет содержательных ответов для оценки")
        return
    ds = Dataset.from_dict(
        {
            "question": [r["question"] for r in answered],
            "answer": [r["answer"] for r in answered],
            "contexts": [r["contexts"] for r in answered],
            "ground_truth": [r["ground_truth"] for r in answered],
        }
    )
    result = evaluate(ds, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])
    print("\n===== RAGAS =====")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
