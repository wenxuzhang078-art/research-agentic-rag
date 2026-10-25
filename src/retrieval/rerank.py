
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def rerank_hits(
    query: str,
    hits: list[dict],
    top_k: int = 3
) -> list[dict]:

    if top_k <= 0:
        raise ValueError("top_k 必须大于0")

    if not hits:
        return []

    base_url = os.getenv("RERANK_BASE_URL")

    if not base_url:
        raise RuntimeError("请先配置 RERANK_BASE_URL")

    # 按原始顺序组织候选文本
    documents = [hit["content"] for hit in hits]

    with OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=base_url
    ) as client:
        response = client.post(
            "/reranks",
            body={
                "model": os.getenv(
                    "RERANK_MODEL", "qwen3-rerank"
                ),
                "query": query,
                "documents": documents,
                "top_n": min(top_k, len(documents))
            },
            cast_to=object
        )

    # 兼容顶层 results 或 output.results 的响应结构
    if not isinstance(response, dict):
        raise RuntimeError("Rerank 响应格式异常")

    ranked = (
        response.get("results")
        or response.get("output", {}).get("results")
    )

    if not ranked:
        raise RuntimeError("Rerank 未返回有效结果")

    final_hits = []

    for item in ranked:
        index = int(item["index"])

        if not 0 <= index < len(hits):
            raise RuntimeError("Rerank 返回非法文档索引")

        original = hits[index]

        final_hits.append({
            **original,
            "rrf_score": original["score"],
            "score": float(item["relevance_score"])
        })

    return final_hits
