"""唯一保留的检索效果评测：Hit@1 / Hit@3 / MRR@3 / Recall@3。"""
import argparse
import json
from pathlib import Path

CASES = Path(__file__).with_name("retrieval_cases.json")


def evaluate(cases: list[dict], retrieve, top_k: int = 3) -> dict[str, float]:
    sums = {"hit1": 0.0, "hit3": 0.0, "mrr3": 0.0, "recall3": 0.0}
    for case in cases:
        ids = [h["chunk_id"] for h in retrieve(case["question"], top_k=top_k)]
        gold = set(case["relevant_chunk_ids"])
        first = next((i for i, cid in enumerate(ids, 1) if cid in gold), None)
        sums["hit1"] += float(first == 1)
        sums["hit3"] += float(first is not None)
        sums["mrr3"] += 1.0 / first if first else 0.0
        sums["recall3"] += len(set(ids) & gold) / len(gold)
        print(f"{case['id']}: 首次命中 {first or '-'}")
    return {k: v / len(cases) for k, v in sums.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-rerank", action="store_true", help="额外评测付费 Rerank API")
    args = parser.parse_args()
    with CASES.open(encoding="utf-8-sig") as f:
        cases = json.load(f)
    from src.retrieval.dense import retrieve
    from src.retrieval.hybrid import retrieve_hybrid, retrieve_hybrid_en, retrieve_hybrid_rerank
    methods = {"Dense": retrieve, "Hybrid": retrieve_hybrid, "Hybrid+EN": retrieve_hybrid_en}
    if args.with_rerank:
        methods["Hybrid+EN+Rerank"] = retrieve_hybrid_rerank
    for name, method in methods.items():
        print(f"\n=== {name} ===")
        result = evaluate(cases, method)
        print("  ".join(f"{key}={value:.4f}" for key, value in result.items()))

if __name__ == "__main__":
    main()
