"""两级 Grade：程序按 Rerank 相关性分数预筛，然后 LLM 审核证据覆盖。"""
from __future__ import annotations

import os
from math import isfinite

from src.agent.context import build_evidence_context
from src.agent.llm import ask_json
from src.agent.prompts import GRADER_PROMPT
from src.agent.state import AgentState


def prefilter_hits(hits: list[dict], *, min_score: float = 0.20) -> tuple[list[dict], dict]:
    """只使用 Qwen Rerank 分数做阈值比较，绝不混用 RRF / COSINE / BM25。

    显式 read_chunk 或 MCP 带来源的证据不具备相同分数尺度，仍交由 LLM 审核。
    未带有效来源或内容的 Chunk 会在 Context Builder 再次剔除。
    """
    if not 0 <= min_score <= 1:
        raise ValueError("GRADE_MIN_RERANK_SCORE 应在 0..1 之间")
    kept, filtered, unscored = [], 0, 0
    for hit in hits:
        if hit.get("score_type") == "rerank_relevance":
            try:
                score = float(hit.get("rerank_score", hit.get("score")))
            except (TypeError, ValueError):
                filtered += 1
                continue
            if not isfinite(score) or score < min_score:
                filtered += 1
                continue
        else:
            unscored += 1
        kept.append(hit)
    return kept, {"input": len(hits), "kept": len(kept), "filtered": filtered,
                  "unscored": unscored, "min_rerank_score": min_score}


async def grader_node(state: AgentState) -> dict:
    threshold = float(os.getenv("GRADE_MIN_RERANK_SCORE", "0.20"))
    filtered, stats = prefilter_hits(state.get("hits", []), min_score=threshold)
    context, candidates = build_evidence_context(filtered)
    if not candidates:
        reason = ("RAG 无命中或全部未达到 Rerank 分数门槛；"
                  "不调用 LLM Grade，交给 Replan 决定补检")
        return {"sufficient": False, "relevant_hits": [],
                "missing_aspects": ["没有达到质量阈值的证据"], "grade_reason": reason,
                "prefilter_stats": stats, "steps": [{"node": "grade", "stats": stats,
                                                     "sufficient": False, "llm_called": False}]}
    try:
        data = await ask_json(GRADER_PROMPT, f"原始问题：{state['question']}\n\n候选证据：\n{context}")
        raw_indices = data.get("relevant_indices", [])
        if not isinstance(raw_indices, list):
            raise ValueError("relevant_indices 不是列表")
        valid = sorted({i for i in raw_indices if type(i) is int and 1 <= i <= len(candidates)})
        missing = data.get("missing_aspects", [])
        if not isinstance(missing, list):
            raise ValueError("missing_aspects 不是列表")
        missing = [str(x).strip() for x in missing if str(x).strip()][:5]
        selected = [candidates[i - 1] for i in valid]
        sufficient = (data.get("sufficient") is True and bool(selected) and not missing)
        reason = str(data.get("reason") or "")
    except Exception as exc:
        sufficient, selected = False, []
        missing = ["证据质量审核失败"]
        reason = f"Grade 调用或格式异常：{type(exc).__name__}"
    return {"sufficient": sufficient, "relevant_hits": selected,
            "missing_aspects": missing, "grade_reason": reason,
            "prefilter_stats": stats,
            "steps": [{"node": "grade", "stats": stats, "llm_called": True,
                       "sufficient": sufficient, "selected": [h["chunk_id"] for h in selected],
                       "missing": missing, "reason": reason}]}
