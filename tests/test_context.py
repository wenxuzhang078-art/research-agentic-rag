import unittest
from src.agent.context import build_evidence_context


class ContextTest(unittest.TestCase):
    def test_budget_and_indices(self):
        hits = [{"chunk_id": f"p{i}", "source": "paper", "page": 1,
                 "content": "evidence " + "x" * 100} for i in range(20)]
        context, selected = build_evidence_context(hits, max_hits=6, max_chars=2000)
        self.assertEqual(len(selected), 6)
        self.assertEqual([h["chunk_id"] for h in selected],
                         ["p0", "p1", "p2", "p17", "p18", "p19"])
        self.assertIn("[6] chunk_id=p19", context)

    def test_dedup(self):
        hit = {"chunk_id": "x", "source": "p", "page": 1, "content": "abc"}
        _, selected = build_evidence_context([hit, hit])
        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
