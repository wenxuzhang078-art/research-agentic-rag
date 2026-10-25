"""Dense cosine retrieval：直接搜索同一个 Hybrid Collection 的 embedding 字段。"""
from __future__ import annotations

from src.embedding.service import embed_texts
from src.storage.milvus import connect_milvus
from src.storage.schema import COLLECTION_NAME


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    if not query.strip() or top_k <= 0:
        raise ValueError("查询不能为空，top_k 必须大于0")
    query_vector = embed_texts([query])[0]
    if len(query_vector) != 1024:
        raise ValueError("Embedding 维度不匹配（应为1024）")

    client = connect_milvus()
    try:
        client.load_collection(collection_name=COLLECTION_NAME)
        result = client.search(
            collection_name=COLLECTION_NAME,
            data=[query_vector],
            anns_field="embedding",
            search_params={"metric_type": "COSINE", "params": {}},
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
