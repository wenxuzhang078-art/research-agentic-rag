"""Milvus Dense + BM25 RRF 融合，并提供可选翻译与 Rerank。"""
from __future__ import annotations

from pymilvus import AnnSearchRequest, RRFRanker

from src.embedding.service import embed_texts
from src.storage.milvus import connect_milvus
from src.storage.schema import COLLECTION_NAME
from src.retrieval.translate import translate_query
from src.retrieval.rerank import rerank_hits


def retrieve_hybrid(
    query: str,
    top_k: int = 3,
    recall_k: int = 20,
    bm25_query: str | None = None,
) -> list[dict]:
    if not query.strip() or top_k <= 0:
        raise ValueError("查询不能为空，top_k 必须大于0")
    recall_k = max(recall_k, top_k)

    dense = AnnSearchRequest(
        data=[embed_texts([query])[0]],
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {}},
        limit=recall_k,
        expr='kb_name == "mvc_research"',
    )
    sparse = AnnSearchRequest(
        data=[bm25_query or query],
        anns_field="content_sparse",
        param={"metric_type": "BM25", "params": {}},
        limit=recall_k,
        expr='kb_name == "mvc_research"',
    )

    client = connect_milvus()
    try:
        client.load_collection(collection_name=COLLECTION_NAME)
        result = client.hybrid_search(
            collection_name=COLLECTION_NAME,
            reqs=[dense, sparse],
            ranker=RRFRanker(k=60),
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


def retrieve_hybrid_en(query: str, top_k: int = 3, recall_k: int = 20) -> list[dict]:
    """Dense 使用原始问题；BM25 使用忠实英文翻译。"""
    return retrieve_hybrid(query, top_k, recall_k, bm25_query=translate_query(query))


def retrieve_hybrid_rerank(query: str, top_k: int = 3, recall_k: int = 20) -> list[dict]:
    """从 Hybrid 召回更多 Chunk，交给 Qwen3 Rerank 精排。"""
    candidates = retrieve_hybrid(query, recall_k, recall_k, bm25_query=translate_query(query))
    return rerank_hits(query=query, hits=candidates, top_k=top_k)
