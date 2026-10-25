
"""ToolRegistry 单元测试：不调用真实 Milvus / LLM。"""

import unittest

from jsonschema.exceptions import ValidationError

from src.tools.registry import ToolRegistry,ToolSpec,tool_registry


class RegistryTest(unittest.IsolatedAsyncioTestCase):

    def test_builtin_tool_schema(self):
        definitions = tool_registry.definitions()

        names = [item["function"]["name"]for item in definitions]
        self.assertIn("rag_search", names)
        self.assertIn("read_chunk", names)

        # 合法参数
        tool_registry.validate("rag_search",{"query": "MVC", "top_k": 3})

        # 超出允许的 top_k 范围
        with self.assertRaises(ValidationError):
            tool_registry.validate("rag_search",{"query": "MVC", "top_k": 999})
        # 缺少必填 query
        with self.assertRaises(ValidationError):
            tool_registry.validate("rag_search",{"top_k": 3})

        # 禁止额外参数
        with self.assertRaises(ValidationError):
            tool_registry.validate("rag_search",{"query": "MVC", "unknown": True})

    # --------------------------------------------------
    # 2. 测试自定义工具的注册和执行
    # --------------------------------------------------
    async def test_custom_tool(self):

        # 独立注册表，不影响内置工具
        registry = ToolRegistry()
        async def fake_tool(args: dict) -> dict:
            return {
                "hits": [
                    {
                        "chunk_id": "a",
                        "content": "MVC paper content",
                        "source": "demo.pdf",
                        "page": 1
                    }
                ]
            }

        spec = ToolSpec(
            name="demo_testing_tool",
            description="测试用的模拟工具",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"],
                "additionalProperties": False
            },
            execute=fake_tool,
        )

        # 注册
        registry.register(spec)

        # 查找
        self.assertEqual(
            registry.get("demo_testing_tool").name,
            "demo_testing_tool"
        )

        # 执行
        result = await registry.execute(
            "demo_testing_tool",
            {"query": "MVC"}
        )

        self.assertEqual(
            result["hits"][0]["chunk_id"],
            "a"
        )

        self.assertEqual(
            result["provider"],
            "local"
        )

        # 重复注册
        with self.assertRaises(ValueError):
            registry.register(spec)

        # 调用不存在的工具
        with self.assertRaises(ValueError):
            await registry.execute(
                "nonexistent",
                {"query": "MVC"}
            )

    # --------------------------------------------------
    # 3. 测试不返回论文证据的普通工具
    # --------------------------------------------------
    async def test_data_tool(self):

        registry = ToolRegistry()
        async def fake_metadata(args: dict) -> dict:
            return {"data": {"paper_id": args["paper_id"],"title": "Demo Paper"}}
        registry.register(
            ToolSpec(
                name="get_metadata",
                description="模拟论文元数据查询",
                parameters={
                    "type": "object",
                    "properties": {
                        "paper_id": {"type": "string"}
                    },
                    "required": ["paper_id"],
                    "additionalProperties": False
                },
                execute=fake_metadata,
                provider="mcp:demo"
            )
        )

        result = await registry.execute("get_metadata",{"paper_id": "123"})
        self.assertEqual(result["hits"], [])
        self.assertEqual(result["data"]["title"],"Demo Paper")
        self.assertEqual(result["provider"],"mcp:demo")


if __name__ == "__main__":
    unittest.main()
