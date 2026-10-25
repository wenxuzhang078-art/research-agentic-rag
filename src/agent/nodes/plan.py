"""外层 Planner 负责制定检索式，不再暴露底层检索器供模型选择。"""
from __future__ import annotations

from src.agent.llm import ask_json
from src.agent.prompts import PLANNER_PROMPT
from src.agent.state import AgentState


async def planner_node(state: AgentState) -> dict:
    question = state["question"].strip()
    if not question:
        raise ValueError("问题不能为空")
    try:
        plan = await ask_json(PLANNER_PROMPT, question)
        query = str(plan.get("search_query") or "").strip() or question
        reason = str(plan.get("reason") or "")
    except Exception as exc:
        query, reason = question, f"规划失败，使用原始问题：{type(exc).__name__}"
    return {
        "search_query": query, "plan_reason": reason,
        "steps": [{"node": "plan", "search_query": query, "reason": reason}],
    }
