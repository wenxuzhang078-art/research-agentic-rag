"""BM25 检索。该索引使用 English Analyzer，中文查询建议使用 translate.py。"""
from __future__ import annotations

from src.storage.milvus import connect_milvus
from src.storage.schema import COLLECTION_NAME


def retrieve_bm25(query: str, top_k: int = 3) -> list[dict]:
    if not query.strip() or top_k <= 0:
        raise ValueError("查询不能为空，top_k 必须大于0")
    client = connect_milvus()
    try:
        client.load_collection(collection_name=COLLECTION_NAME)
        result = client.search(
            collection_name=COLLECTION_NAME,
            data=[query],
            anns_field="content_sparse",
            search_params={"metric_type": "BM25", "params": {}},
            filter='kb_name == "mvc_research"',
            limit=top_k,
            output_fields=["chunk_id", "content", "source", "page"],
            consistency_level="Strong",
        )
        return [
            {
                "chunk_id": (hit.get("entity") or {}).get("chunk_id", hit.get("id")),
                "score": float(hit["distance"]),
                "content": (hit.get("entity") or {}).get("content", ""),
                "source": (hit.get("entity") or {}).get("source", ""),
                "page": (hit.get("entity") or {}).get("page"),
            }
            for hit in (result[0] if result else [])
        ]
    finally:
        client.close()
