
from __future__ import annotations

import asyncio

from src.agent.prompts import INSUFFICIENT_EVIDENCE
from src.agent.state import AgentState
from src.rag.answer import generate_answer


async def generator_node(state: AgentState) -> dict:
    hits = state.get("relevant_hits", [])
    sufficient = state.get("sufficient", False)
    missing = state.get("missing_aspects", [])

    # 情况1：完全没有可用证据
    if not hits:
        answer = INSUFFICIENT_EVIDENCE

        if state.get("tool_errors"):
            answer += " 检索工具发生错误，请检查执行轨迹。"

        status = "none"

    # 情况2：有直接证据，但不能完整满足要求
    elif not sufficient:
        partial_answer = await asyncio.to_thread(
            generate_answer,
            state["question"],
            hits
        )

        answer = (
            "以下是目前检索证据能够支持的部分信息，"
            "不代表完整资料：\n\n"
            + partial_answer
        )

        if missing:
            answer += (
                "\n\n尚缺少可靠证据的信息："
                + "、".join(missing)
                + "。"
            )

        status = "partial"

    # 情况3：证据能够满足当前问题
    else:
        answer = await asyncio.to_thread(
            generate_answer,
            state["question"],
            hits
        )

        status = "full"

    return {
        "answer": answer,
        "steps": [{
            "node": "generate",
            "answer_status": status,
            "cited_hit_count": len(hits),
        }],
    }
