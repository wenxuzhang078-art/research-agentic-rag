"""无需真实模型、Milvus 的 Graph 路由测试。
运行：python -m unittest tests.test_graph -v
"""
import asyncio
import unittest

from src.agent.graph import build_graph


class GraphRouteTest(unittest.TestCase):
    def test_replan_and_stop_at_two_acts(self):
        async def plan(state):
            return {"actions": [{"tool": "dense_search", "arguments": {"query": state["question"]}}],
                    "steps": [{"node": "plan"}]}

        async def act(state):
            return {"attempts": state.get("attempts", 0) + 1,
                    "hits": [{"chunk_id": "doc1", "content": "evidence", "source": "doc", "page": 1}],
                    "steps": [{"node": "act"}]}

        async def grade(state):
            enough = state.get("attempts", 0) == 2
            return {"sufficient": enough,
                    "relevant_hits": state["hits"] if enough else [],
                    "missing_aspects": [] if enough else ["label loss"],
                    "steps": [{"node": "grade"}]}

        async def replan(state):
            return {"actions": [{"tool": "hybrid_en_search", "arguments": {"query": "label loss"}}],
                    "steps": [{"node": "replan"}]}

        async def generate(state):
            return {"answer": "mock answer", "steps": [{"node": "generate"}]}

        graph = build_graph({"plan": plan, "act": act, "grade": grade,
                             "replan": replan, "generate": generate})
        result = asyncio.run(graph.ainvoke({"question": "MVC consistency",
                                           "attempts": 0, "steps": []}))
        self.assertEqual(result["attempts"], 2)
        self.assertTrue(result["sufficient"])
        self.assertEqual(result["answer"], "mock answer")
        self.assertEqual([s["node"] for s in result["steps"]],
                         ["plan", "act", "grade", "replan", "act", "grade", "generate"])

    def test_no_infinite_loop_after_two_attempts(self):
        async def plan(state):
            return {"actions": [], "steps": []}

        async def act(state):
            return {"attempts": state.get("attempts", 0) + 1, "steps": []}

        async def grade(state):
            return {"sufficient": False, "missing_aspects": ["no evidence"], "steps": []}

        async def replan(state):
            return {"actions": [], "steps": []}

        async def generate(state):
            return {"answer": "insufficient", "steps": []}

        graph = build_graph({"plan": plan, "act": act, "grade": grade,
                             "replan": replan, "generate": generate})
        result = asyncio.run(graph.ainvoke({"question": "test", "attempts": 0,
                                           "steps": []}))
        self.assertEqual(result["attempts"], 2)
        self.assertFalse(result["sufficient"])
        self.assertEqual(result["answer"], "insufficient")


if __name__ == "__main__":
    unittest.main()
