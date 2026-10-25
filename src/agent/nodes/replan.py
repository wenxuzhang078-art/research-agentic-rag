"""外层自纠错：利用 Grade 缺口重新制定检索式，然后返回 Act。"""
from __future__ import annotations

from src.agent.llm import ask_json
from src.agent.prompts import REPLAN_PROMPT
from src.agent.state import AgentState


async def replanner_node(state: AgentState) -> dict:
    old_query = state.get("search_query") or state["question"]
    missing = state.get("missing_aspects") or []
    prompt = (f"用户问题：{state['question']}\n上一轮检索式：{old_query}\n"
              f"证据缺失：{missing}\nGrade 理由：{state.get('grade_reason', '')}")
    try:
        response = await ask_json(REPLAN_PROMPT, prompt)
        new_query = str(response.get("search_query") or "").strip()
    except Exception:
        new_query = ""
    if not new_query or new_query == old_query:
        # 避免无意义重复；针对缺口做定向兜底。
        new_query = f"{state['question']} {' '.join(missing)}".strip()
    return {"search_query": new_query, "steps": [
        {"node": "replan", "search_query": new_query, "missing": missing},
    ]}
