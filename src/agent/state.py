"""外层 LangGraph State；工具调用详细历史在 Act 局部，不无限写入 State。"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    # 问题 + Plan
    question: str
    search_query: str
    plan_reason: str
    # Act：候选池与少量诊断信息
    hits: list[dict[str, Any]]
    attempts: int
    tool_errors: list[str]
    tool_results: list[dict[str, Any]]
    # Grade：检索分数过滤之后的审核结果
    relevant_hits: list[dict[str, Any]]
    sufficient: bool
    missing_aspects: list[str]
    grade_reason: str
    prefilter_stats: dict[str, Any]
    # 最终结果
    answer: str
    steps: Annotated[list[dict[str, Any]], operator.add]
