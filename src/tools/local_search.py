"""提供给 Agent 的业务级工具；底层 Dense/BM25 是 RAG 内部实现细节。"""
from __future__ import annotations

import asyncio
import json


async def rag_search(query: str, top_k: int = 8) -> dict:
    from src.rag.service import search_rag
    hits = await asyncio.to_thread(search_rag, query, top_k=top_k)
    return {"hits": hits, "provider": "rag", "data": {"count": len(hits)}}


async def read_chunk(chunk_id: str) -> dict:
    """按 Milvus 主键续读一个 Chunk，确保来源可追溯。"""
    def _read() -> list[dict]:
        from src.storage.milvus import connect_milvus
        from src.storage.schema import COLLECTION_NAME
        client = connect_milvus()
        try:
            records = client.query(
                collection_name=COLLECTION_NAME,
                filter=f"chunk_id == {json.dumps(chunk_id, ensure_ascii=False)} and kb_name == \"mvc_research\"",
                output_fields=["chunk_id", "content", "source", "page"],
                limit=1,
            )
            return [
                {"chunk_id": row["chunk_id"], "content": row["content"],
                 "source": row["source"], "page": row["page"],
                 "score": None, "score_type": "unscored_read"}
                for row in records
            ]
        finally:
            client.close()

    hits = await asyncio.to_thread(_read)
    return {"hits": hits, "provider": "local", "data": {"count": len(hits)}}
