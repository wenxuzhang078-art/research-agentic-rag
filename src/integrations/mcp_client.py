"""MCP stdio 工具发现与注册；将 Server 的 stderr 写到诊断文件。"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.tools.registry import ToolSpec, tool_registry
from src.integrations.arxiv_adapter import arxiv_to_hits

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = PROJECT_ROOT / "logs" / "mcp_stderr.log"

@asynccontextmanager
async def _open_session(params: StdioServerParameters):
    # MCP stdio 子进程的 stderr 不属于协议数据；独立记录便于定位启动异常。
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def register_stdio_mcp(
    *,
    server_id: str,
    command: str,
    args: list[str],
    allowed_tools: set[str],
) -> list[str]:
    """从受信任的 stdio Server 发现并注册白名单中的工具。"""
    params = StdioServerParameters(
        command=command,
        args=args,
        cwd=str(PROJECT_ROOT),
        env={"PYTHONIOENCODING": "utf-8"},
    )
    # 通过 stdio 会话发现远端工具。
    async with _open_session(params) as session:
        remote_tools = (await session.list_tools()).tools

    registered: list[str] = []
    for remote_tool in remote_tools:
        if remote_tool.name not in allowed_tools:
            continue

        remote_name = remote_tool.name
        public_name = f"mcp_{server_id}_{remote_name}"
        # MCP SDK 1.x / 2.x 的字段命名不同。
        schema = getattr(remote_tool, "inputSchema", None) or getattr(remote_tool, "input_schema", None)
        if not isinstance(schema, dict):
            raise TypeError(f"MCP 工具没有合法 JSON Schema：{remote_name}")

        async def invoke(arguments: dict[str, Any], *, _remote_name: str = remote_name) -> dict[str, Any]:
            async with _open_session(params) as session:
                response = await session.call_tool(_remote_name, arguments=arguments)

            if getattr(response, "is_error", getattr(response, "isError", False)):
                detail = "\n".join(
                    str(block.text) for block in response.content
                    if getattr(block, "type", None) == "text"
                )
                raise RuntimeError(f"MCP 工具执行失败：{_remote_name}：{detail[:600]}")

            payload = getattr(response, "structured_content", None)
            if payload is None:
                payload = getattr(response, "structuredContent", None)
            if not isinstance(payload, dict):
                texts = [
                    block.text for block in response.content
                    if getattr(block, "type", None) == "text"
                ]
                try:
                    payload = json.loads("\n".join(texts))
                except (ValueError, TypeError):
                    payload = {"text": "\n".join(texts)}

            if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
                payload = payload["result"]

            if not isinstance(payload, dict):
                raise TypeError("MCP 返回内容不是 JSON 对象")

            # 第三方服务可能用普通 JSON 表示业务错误，
            # 此时 MCP 的 isError 不一定为 True。
            status = payload.get("status")

            if status in {"error", "rate_limited", "unavailable"}:
                raise RuntimeError(
                    f"arXiv MCP 返回 {status}: "
                    f"{str(payload.get('message', ''))[:300]}"
                )

            if server_id == "arxiv" and _remote_name in {"search_papers","get_abstract",}:
                # arXiv 专用适配器
                hits = arxiv_to_hits(
                    _remote_name,
                    payload,
                    arguments
                )

                if _remote_name == "search_papers":
                    raw_count = len(payload.get("papers", []))
                else:
                    raw_count = 1 if hits else 0

            else:
                # 其他 MCP 工具暂时沿用标准 hits 接口
                raw_hits = payload.get("hits", [])

                if not isinstance(raw_hits, list):
                    raise TypeError("MCP hits 必须是列表")

                hits = []
                for hit in raw_hits[:20]:
                    if not isinstance(hit, dict):
                        continue
                    if not all(
                            isinstance(hit.get(k), str) and hit[k]
                            for k in ("chunk_id", "content", "source")
                    ):
                        continue
                    if type(hit.get("page")) is not int:
                        continue

                    hits.append({
                        **hit,
                        "chunk_id": (
                            f"mcp:{server_id}:{_remote_name}:"
                            f"{hit['chunk_id']}"
                        ),
                        "external_chunk_id": hit["chunk_id"],
                        "score_type": "unscored_external",
                    })

                raw_count = len(raw_hits)

            return {"hits": hits,"data": payload,"provider": f"mcp:{server_id}","raw_count": raw_count,}

        tool_registry.register(
            ToolSpec(
                name=public_name,
                description=(
                    f"通过 MCP ({server_id}) 调用只读工具："
                    f"{remote_tool.description or remote_name}"
                ),
                parameters=schema,
                execute=invoke,
                provider=f"mcp:{server_id}",
            )
        )
        registered.append(public_name)
    return registered
