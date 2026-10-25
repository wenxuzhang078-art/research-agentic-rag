"""外层 Act = 固定的完整 RAG 预取 + 有预算的内层 ReAct 工具循环。"""
from __future__ import annotations

from src.agent.react import react_collect
from src.agent.state import AgentState
from src.tools.registry import tool_registry


def _merge_hits(old_hits: list[dict], new_hits: list[dict]) -> list[dict]:
    """按 Chunk 去重；若重复命中带来更高 Rerank 分数则优先保留。"""
    merged = {str(h["chunk_id"]): h for h in old_hits if h.get("chunk_id")}
    for hit in new_hits:
        chunk_id = str(hit.get("chunk_id") or "")
        if not chunk_id:
            continue
        prior = merged.get(chunk_id)
        if prior is None:
            merged[chunk_id] = hit
        elif (hit.get("score_type") == "rerank_relevance" and
              (prior.get("score_type") != "rerank_relevance" or
               float(hit.get("rerank_score", 0)) > float(prior.get("rerank_score", 0)))):
            merged[chunk_id] = hit
    return list(merged.values())


async def actor_node(state: AgentState) -> dict:
    query = state.get("search_query") or state["question"]
    hits = list(state.get("hits", [])) #如果有hits就给我  没有就给我空列表[]
    errors = list(state.get("tool_errors", []))
    calls: list[dict] = []
    observations = list(state.get("tool_results", []))

    # 每一轮 Act 都执行一次完整 RAG
    try:
        result = await tool_registry.execute("rag_search", {"query": query, "top_k": 8})
        hits = _merge_hits(hits, result["hits"])
        calls.append({"tool": "rag_search", "query": query, "returned": len(result["hits"]),
                      "phase": "prefetch"})
    except Exception as exc:
        detail = f"rag_search: {type(exc).__name__}: {str(exc)[:200]}"
        errors.append(detail)
        calls.append({"tool": "rag_search", "query": query, "error": detail})

    # 即便预取失败，内层可尝试自有工具/MCP 进行补检。
    inner = await react_collect(
        state["question"], search_query=query, existing_hits=hits,
        missing_aspects=state.get("missing_aspects"),  #missing_aspects 上一轮grade 判定“还缺啥”
    )
    hits = _merge_hits(hits, inner["hits"])
    calls.extend(inner["calls"])
    errors.extend(inner["errors"])
    observations.extend(inner["observations"])

    return {
        "hits": hits,
        "attempts": state.get("attempts", 0) + 1,
        "tool_errors": errors,
        "tool_results": observations[-20:],
        "steps": [{"node": "act", "search_query": query, "calls": calls,
                   "total_hits": len(hits), "errors": errors[-3:]}],
    }
