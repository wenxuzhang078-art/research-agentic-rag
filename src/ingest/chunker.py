"""稳定的页内字符分块规则，保持旧有 Chunk ID，便于复用 Milvus 数据。"""
from __future__ import annotations


def split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("必须满足 chunk_size > 0 且 0 <= chunk_overlap < chunk_size")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - chunk_overlap
    return chunks


def split_documents(documents: list[dict], chunk_size: int = 800, chunk_overlap: int = 100) -> list[dict]:
    return [
        {"chunk_id": f"{doc['source']}_p{doc['page']}_c{i}",
         "source": doc["source"], "page": doc["page"], "content": part}
        for doc in documents
        for i, part in enumerate(split_text(doc["content"], chunk_size, chunk_overlap))
    ]
