"""Context Engineering：去重、裁剪、编号、来源绑定。"""
from __future__ import annotations

from typing import Any


def build_evidence_context(
    hits: list[dict[str, Any]],
    *,
    max_hits: int = 12,
    max_chars: int = 14000,
    max_chunk_chars: int = 1200,
) -> tuple[str, list[dict[str, Any]]]:
    """返回 (有编号的上下文, 与编号一一对应的片段)。

    max_chars 为简单字符预算；以后可替换为 tokenizer 的 Token 预算。
    """
    parts: list[str] = []
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    used = 0

    # Replan 的新证据被追加在 hits 尾部。保留前部高排名证据，也保留尾部新证据；
    # 否则一旦原始候选超过 max_hits，重检索内容可能永远进不了 Grade。
    if len(hits) > max_hits:
        newest_count = max_hits // 2
        candidates = hits[:max_hits - newest_count] + hits[-newest_count:]
    else:
        candidates = hits

    for hit in candidates:
        chunk_id = str(hit.get("chunk_id", ""))
        content = str(hit.get("content", "")).strip()
        if not chunk_id or not content or chunk_id in seen:
            continue
        if len(selected) >= max_hits:
            break
        seen.add(chunk_id)
        preview = content[:max_chunk_chars]
        locator = (
            f"page={hit['page']}"
            if isinstance(hit.get("page"), int)
            else f"url={hit.get('source_url', '')}"
        )
        block = (
            f"[{len(selected) + 1}] chunk_id={chunk_id}\n"
            f"source={hit.get('source', '')}; {locator}\n"
            f"content:\n{preview}"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        selected.append({**hit, "content": preview})
        used += len(block)

    return "\n\n".join(parts), selected
