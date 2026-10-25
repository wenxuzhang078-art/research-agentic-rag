"""CLI 的 MCP 参数转发与部分证据输出；不调用外部服务。"""
from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

import main


class CliTest(unittest.TestCase):
    def test_mcp_config_and_partial_sources(self):
        config = {"server_id": "demo", "command": "demo-server",
                  "args": ["--stdio"], "allowed_tools": ["search"]}
        mcp_module = ModuleType("src.integrations.mcp_client")
        mcp_module.register_stdio_mcp = AsyncMock(return_value=["mcp_demo_search"])
        graph_module = ModuleType("src.agent.graph")
        graph_module.graph = SimpleNamespace(ainvoke=AsyncMock(return_value={
            "answer": "部分回答[1]", "sufficient": False,
            "relevant_hits": [{"source": "arXiv:1706.03762", "page": None,
                               "source_url": "https://arxiv.org/abs/1706.03762",
                               "chunk_id": "arxiv:1706.03762"}],
        }))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            args = main.create_parser().parse_args(["agent", "--mcp-config", str(path)])
            output = io.StringIO()
            with patch.dict("sys.modules", {"src.integrations.mcp_client": mcp_module,
                                            "src.agent.graph": graph_module}), redirect_stdout(output):
                asyncio.run(main.run_agent(args, "测试问题"))
        mcp_module.register_stdio_mcp.assert_awaited_once_with(
            server_id="demo", command="demo-server", args=["--stdio"], allowed_tools={"search"},
        )
        graph_module.graph.ainvoke.assert_awaited_once()
        self.assertIn("https://arxiv.org/abs/1706.03762", output.getvalue())
        self.assertNotIn("第None页", output.getvalue())


if __name__ == "__main__":
    unittest.main()
