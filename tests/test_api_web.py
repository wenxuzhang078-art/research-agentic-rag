"""FastAPI 接口契约测试；不连接 Qwen、Milvus 或 MCP。"""
from __future__ import annotations

import tempfile
import os
import json
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, patch
import sys

from fastapi.testclient import TestClient
import importlib

api = importlib.import_module("src.api.app")


class ApiWebTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"MCP_CONFIG_PATH": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.client_context = TestClient(api.app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_health_and_status(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/api/status").json()["mcp_status"], "disabled")
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")

    def test_rag_chat_maps_sources(self):
        fake = {"answer": "示例回答[1]", "sources": [{
            "chunk_id": "p1_c2", "source": "paper.pdf", "page": 1,
            "content": "论文段落", "rerank_score": 0.72, "score_type": "rerank_relevance",
        }]}
        with patch.object(api, "_run_rag_sync", return_value=fake) as runner:
            response = self.client.post("/api/chat", json={"question": "MVC 是什么？", "mode": "rag"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["sources"][0]["page"], 1)
        self.assertEqual(data["sources"][0]["score"], 0.72)
        self.assertEqual(data["steps"], [])
        runner.assert_called_once_with("MVC 是什么？", 5)

    def test_agent_chat_external_source_and_trace(self):
        fake = {"answer": "Transformer 作者在此[1]", "sufficient": True, "attempts": 1,
                "steps": [{"node": "plan"}, {"node": "act"}, {"node": "generate"}],
                "relevant_hits": [{"chunk_id": "arxiv:1706.03762", "page": None,
                                   "source": "arXiv:1706.03762", "content": "Authors: ...",
                                   "source_url": "https://arxiv.org/abs/1706.03762",
                                   "score_type": "unscored_external", "provider": "mcp:arxiv"}]}
        with patch.object(api, "_run_agent", new_callable=AsyncMock, return_value=fake) as runner:
            response = self.client.post("/api/chat", json={"question": "谁写了 Transformer？", "mode": "agent"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["sources"][0]["score"])
        self.assertEqual(data["sources"][0]["source_url"], "https://arxiv.org/abs/1706.03762")
        self.assertEqual(data["steps"][0]["node"], "plan")
        runner.assert_awaited_once()

    def test_invalid_request_and_upload(self):
        self.assertEqual(self.client.post("/api/chat", json={"question": " ", "mode": "rag"}).status_code, 422)
        self.assertEqual(self.client.post("/api/chat", json={"question": "ok", "mode": "invalid"}).status_code, 422)
        self.assertEqual(self.client.post("/api/documents/upload", files={"file": ("a.txt", b"bad", "text/plain")}).status_code, 400)
        self.assertEqual(self.client.post("/api/documents/upload", files={"file": ("a.pdf", b"bad", "application/pdf")}).status_code, 400)

    def test_upload_and_document_listing(self):
        fake = ModuleType("src.ingest.service")
        fake.ingest_pdf = lambda path: {"pdf": Path(path).name, "pages": 1, "chunks": 2}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(api, "PAPERS_DIR", Path(tmp)), patch.dict(sys.modules, {"src.ingest.service": fake}):
                response = self.client.post("/api/documents/upload", files={"file": ("sample.pdf", b"%PDF-1.4\nmock", "application/pdf")})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["result"]["chunks"], 2)
                docs = self.client.get("/api/documents").json()["documents"]
                self.assertEqual(len(docs), 1)
                self.assertTrue(docs[0]["filename"].endswith(".pdf"))


class ApiMcpLifespanTest(unittest.TestCase):
    def test_config_registers_mcp_at_startup(self):
        config = {"server_id": "demo", "command": "demo-server",
                  "args": ["--stdio"], "allowed_tools": ["search"]}
        fake = ModuleType("src.integrations.mcp_client")
        fake.register_stdio_mcp = AsyncMock(return_value=["mcp_demo_search"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with patch.dict(os.environ, {"MCP_CONFIG_PATH": str(path)}), \
                    patch.dict(sys.modules, {"src.integrations.mcp_client": fake}):
                with TestClient(api.app) as client:
                    data = client.get("/api/status").json()
        self.assertEqual(data["mcp_status"], "connected")
        self.assertEqual(data["mcp_tools"], ["mcp_demo_search"])
        fake.register_stdio_mcp.assert_awaited_once_with(
            server_id="demo", command="demo-server", args=["--stdio"],
            allowed_tools={"search"},
        )

    def test_mcp_failure_keeps_api_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing.json")
            with patch.dict(os.environ, {"MCP_CONFIG_PATH": missing}), \
                    patch.object(api.log, "exception"):
                with TestClient(api.app) as client:
                    self.assertEqual(client.get("/api/status").json()["mcp_status"], "error")
                    self.assertEqual(client.get("/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
