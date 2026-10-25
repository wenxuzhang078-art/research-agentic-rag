"""Act 内层有界 ReAct：Qwen 原生 tool_calls → Registry/MCP → tool 消息反馈给 Qwen。

外层 LangGraph 仍负责 Plan/Grade/Replan/Generate；本层不生成用户最终答案。
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.agent.prompts import REACT_PROMPT
from src.tools.registry import tool_registry

load_dotenv()
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 4
MAX_MODEL_CONTEXT_CHARS = 6500
MAX_TOOL_RESULT_CHARS = 3000


def _preview_hits(hits: list[dict]) -> str:
    lines = []
    for hit in hits[:6]:
        lines.append(
            f"chunk_id={hit.get('chunk_id')} / score={hit.get('rerank_score', 'unscored')} / "
            f"page={hit.get('page')} / {str(hit.get('content', ''))[:350]}"
        )
    return "\n".join(lines)[:MAX_MODEL_CONTEXT_CHARS]


def _model_turn(messages: list[dict], tool_specs: list[dict], *, allow_tools: bool):
    """单次聊天模型调用；从线程运行避免阻塞 async Graph。"""
    with OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ["DASHSCOPE_BASE_URL"],
        timeout=60, max_retries=1,
    ) as client:
        return client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-plus"),
            temperature=0,
            messages=messages,
            tools=tool_specs,
            tool_choice="auto" if allow_tools else "none",
        )


async def react_collect(
    question: str,
    *,  #强制关键字参数
    search_query: str,
    existing_hits: list[dict],
    missing_aspects: list[str] | None = None,
) -> dict[str, Any]:

    tool_specs = tool_registry.definitions()  #工具目录，工具的描述，工具所需要的参数
    if not tool_specs:
        return {"hits": [], "calls": [], "errors": [], "observations": []}

    messages: list[dict] = [
        {"role": "system", "content": REACT_PROMPT},
        {"role": "user", "content": (
            f"原始问题：{question}\n本轮计划检索式：{search_query}\n"
            f"待补充方面：{missing_aspects or []}\n"
            f"已预取的 RAG 证据（仅展示前6条）：\n{_preview_hits(existing_hits)}\n"
            "请检查是否需要调用额外工具补充证据。"
        )},
    ]
    extra_hits: list[dict] = []
    calls: list[dict] = []
    errors: list[str] = []
    observations: list[dict] = []
    used: set[tuple[str, str]] = set()
    tool_count = 0

    for turn in range(MAX_TOOL_ROUNDS + 1):
        can_call = turn < MAX_TOOL_ROUNDS and tool_count < MAX_TOOL_CALLS #can_call 是一个布尔开关
        try:
            result = await asyncio.to_thread(_model_turn, messages, tool_specs, allow_tools=can_call)
        except Exception as exc:
            errors.append(f"ReAct 模型调用失败：{type(exc).__name__}: {str(exc)[:150]}")
            break
        message = result.choices[0].message
        requested = [c for c in (message.tool_calls or []) if c.type == "function"] #从大模型返回消息里，筛选出所有类型为 function 的工具调用请求
        if not requested or not can_call:
            break

        # 保留原始 Tool Call ID，将每个结果回传对应的 role=tool。
        messages.append({
            "role": "assistant", "content": message.content or "",
            "tool_calls": [
                {"id": call.id, "type": "function", "function": {
                    "name": call.function.name, "arguments": call.function.arguments,
                }} for call in requested
            ],
        })
        for call in requested: #遍历类型为 function 的工具调
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments 不是 JSON 对象")
                signature = (name, json.dumps(args, ensure_ascii=False, sort_keys=True))
                if signature in used:
                    raise ValueError("重复工具调用被跳过")
                if tool_count >= MAX_TOOL_CALLS:
                    raise ValueError("已达到内层工具调用上限")
                used.add(signature)
                tool_count += 1
                output = await tool_registry.execute(name, args)
                hits = output.get("hits", [])[:20]
                extra_hits.extend(hits)
                # 模型只看到限长摘要。完整已验证证据独立存入结构化池。
                observation = {
                    "provider": output.get("provider", "local"),
                    "count": len(hits),
                    "hits": [
                        {"chunk_id": h.get("chunk_id"), "source": h.get("source"),
                         "page": h.get("page"), "score": h.get("rerank_score"),
                         "content": str(h.get("content", ""))[:350]} for h in hits[:4]
                    ],
                    "data": output.get("data"),
                }
                observations.append({"tool": name, "count": len(hits),
                                     "provider": output.get("provider", "local")})
                calls.append({"tool": name,"arguments": args,"raw_count": output.get("raw_count", len(hits)),"returned": len(hits)})

                feedback = json.dumps(observation, ensure_ascii=False, default=str)[:MAX_TOOL_RESULT_CHARS]
            except Exception as exc:
                detail = f"{name}: {type(exc).__name__}: {str(exc)[:200]}"
                errors.append(detail)
                calls.append({"tool": name, "error": detail})
                feedback = json.dumps({"error": detail}, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": feedback})
    return {"hits": extra_hits, "calls": calls, "errors": errors,
            "observations": observations}
