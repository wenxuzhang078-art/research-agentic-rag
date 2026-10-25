import unittest
from src.ingest.chunker import split_documents

class IngestionTest(unittest.TestCase):
    def test_stable_chunk_ids(self):
        pages = [{"source": "test.pdf", "page": 1, "content": "abc" * 100}]
        chunks = split_documents(pages, chunk_size=100, chunk_overlap=20)
        self.assertEqual(chunks[0]["chunk_id"], "test.pdf_p1_c0")
        self.assertEqual(chunks[1]["chunk_id"], "test.pdf_p1_c1")
        self.assertTrue(all(x["source"] == "test.pdf" for x in chunks))

if __name__ == "__main__":
    unittest.main()
