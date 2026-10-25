"""阿里云百炼 text-embedding-v4，维度必须与 Milvus Schema 一致（1024）。"""
from __future__ import annotations

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def embed_texts(texts: list[str], batch_size: int = 10) -> list[list[float]]:
    if batch_size <= 0:
        raise ValueError("batch_size 必须大于0")
    if not texts:
        return []
    result: list[list[float]] = []
    with OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ["DASHSCOPE_BASE_URL"],
        timeout=60,
    ) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            response = client.embeddings.create(
                model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
                input=batch,
                dimensions=1024,
            )
            ordered = sorted(response.data, key=lambda x: x.index)
            vectors = [item.embedding for item in ordered]
            if len(vectors) != len(batch) or any(len(v) != 1024 for v in vectors):
                raise ValueError("Embedding 返回维度或数量错误")
            result.extend(vectors)
    return result
