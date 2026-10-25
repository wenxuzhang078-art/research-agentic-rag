"""MCP SDK 字段兼容与证据适配；不启动真实 stdio Server。"""
from __future__ import annotations

import json
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.integrations import mcp_client
from src.tools.registry import ToolRegistry


class McpClientTest(unittest.IsolatedAsyncioTestCase):
    async def invoke_search(self, response, *, legacy=False):
        registry = ToolRegistry()
        schema = {"type": "object", "properties": {"query": {"type": "string"}},
                  "required": ["query"], "additionalProperties": False}
        tool = SimpleNamespace(name="search_papers", description="搜索论文",
                               **{"inputSchema" if legacy else "input_schema": schema})
        session = SimpleNamespace(
            list_tools=AsyncMock(return_value=SimpleNamespace(tools=[tool])),
            call_tool=AsyncMock(return_value=response),
        )

        @asynccontextmanager
        async def fake_session(params):
            yield session

        with patch.object(mcp_client, "tool_registry", registry), \
                patch.object(mcp_client, "_open_session", fake_session):
            names = await mcp_client.register_stdio_mcp(
                server_id="arxiv", command="fake-server", args=[], allowed_tools={"search_papers"},
            )
            self.assertEqual(names, ["mcp_arxiv_search_papers"])
            return await registry.execute(names[0], {"query": "multi-view clustering"})

    async def test_snake_case_structured_content(self):
        response = SimpleNamespace(is_error=False, content=[], structured_content={
            "papers": [{"id": "1706.03762", "title": "Test paper", "abstract": "Evidence"}],
        })
        result = await self.invoke_search(response)
        self.assertEqual(result["hits"][0]["source_url"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(result["raw_count"], 1)

    async def test_legacy_text_response(self):
        payload = {"papers": [{"id": "1706.03762", "title": "Test paper"}]}
        response = SimpleNamespace(isError=False, structuredContent=None,
                                   content=[SimpleNamespace(type="text", text=json.dumps(payload))])
        result = await self.invoke_search(response, legacy=True)
        self.assertEqual(result["hits"][0]["chunk_id"], "arxiv:1706.03762")

    async def test_legacy_error_is_not_usable_evidence(self):
        response = SimpleNamespace(isError=True,
                                   content=[SimpleNamespace(type="text", text="rate limited")])
        with self.assertRaisesRegex(RuntimeError, "rate limited"):
            await self.invoke_search(response, legacy=True)


if __name__ == "__main__":
    unittest.main()
