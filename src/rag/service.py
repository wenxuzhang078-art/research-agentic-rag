"""唯一 RAG 门面：完整检索（Dense + BM25 → RRF → Rerank）与按证据回答。"""
from __future__ import annotations

from src.rag.answer import generate_answer


def search_rag(question: str, *, top_k: int = 8, recall_k: int = 20) -> list[dict]:
    """单一检索入口，Agent 不得直接调用 Dense 或 BM25。

    对中文问题：Dense 使用原问题，BM25 使用忠实英文查询；两路结果在 Milvus
    内使用 RRF 融合，再调用 Qwen3-Rerank 对候选片段精排。
    最终 score 为 rerank relevance_score，而不是 RRF 分数。
    """
    if not question.strip() or not (1 <= top_k <= 20):
        raise ValueError("检索问题不能为空，top_k 必须为 1..20")
    from src.retrieval.hybrid import retrieve_hybrid_rerank

    hits = retrieve_hybrid_rerank(
        question, top_k=top_k, recall_k=max(recall_k, top_k)
    )
    return [
        {**hit,
         "rerank_score": float(hit["score"]),
         "score_type": "rerank_relevance"}
        for hit in hits
    ]


def ask_rag(question: str, *, top_k: int = 5) -> dict:
    """保留纯 RAG CLI：不调用 Planner/React/Grade，直接基于完整 RAG 生成。"""
    hits = search_rag(question, top_k=top_k)
    return {
        "question": question,
        "mode": "dense_bm25_rrf_rerank",
        "answer": generate_answer(question, hits),
        "sources": hits,
    }
