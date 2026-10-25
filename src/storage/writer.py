"""唯一的 Milvus 写入入口，写入 Hybrid Collection。"""
from __future__ import annotations

from pymilvus import MilvusClient
from src.storage.schema import COLLECTION_NAME


def upsert_chunks(client: MilvusClient, chunks: list[dict], embeddings: list[list[float]]) -> dict:
    if not chunks or len(chunks) != len(embeddings):
        raise ValueError("Chunk 非空且与 Embedding 数量一致")
    ids = [chunk["chunk_id"] for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("当前批次存在重复 Chunk ID")

    rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        if len(vector) != 1024:
            raise ValueError(f"第 {index} 条向量维度错误，要求1024")
        rows.append({
            "chunk_id": chunk["chunk_id"],
            "embedding": vector,
            "content": chunk["content"],
            "kb_name": "mvc_research",
            "document_id": chunk["source"],
            "version_id": 1,
            "chunk_index": index,
            "source": chunk["source"],
            "page": chunk["page"],
        })
    return client.upsert(collection_name=COLLECTION_NAME, data=rows)
