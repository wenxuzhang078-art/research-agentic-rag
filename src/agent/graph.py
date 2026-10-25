"""外层 Plan → Act → Grade → Replan → Generate 编排。"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agent.state import AgentState
from src.agent.nodes.plan import planner_node
from src.agent.nodes.act import actor_node
from src.agent.nodes.grade import grader_node
from src.agent.nodes.replan import replanner_node
from src.agent.nodes.answer import generator_node

MAX_ACT_ATTEMPTS = 2


def route_after_grade(state: AgentState) -> str:
    if state.get("sufficient"):
        return "generate"
    if state.get("attempts", 0) >= MAX_ACT_ATTEMPTS:
        return "generate"
    return "replan"


def build_graph(nodes: dict[str, Any] | None = None):
    # 支持单测时替换节点，不影响生产 Graph。
    resolved = {
        "plan": planner_node,
        "act": actor_node,
        "grade": grader_node,
        "replan": replanner_node,
        "generate": generator_node,
    }

    if nodes:
        invalid = set(nodes) - set(resolved)
        if invalid:
            raise ValueError(f"未知节点：{invalid}")
        resolved.update(nodes)

    builder = StateGraph(AgentState)

    for name, node in resolved.items():
        builder.add_node(name, node)


    builder.add_edge(START, "plan")
    builder.add_edge("plan", "act")
    builder.add_edge("act", "grade")
    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {"replan": "replan", "generate": "generate"},
    )
    builder.add_edge("replan", "act")
    builder.add_edge("generate", END)
    return builder.compile()


graph = build_graph()
