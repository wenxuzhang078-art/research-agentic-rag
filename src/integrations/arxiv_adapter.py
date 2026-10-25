
"""把 arXiv MCP 返回的论文元数据转换为统一 Evidence。"""

import re
from typing import Any


ARXIV_ID = re.compile(
    r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
)


def arxiv_to_hits(
    tool_name: str,
    payload: dict[str, Any],
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:

    if tool_name == "search_papers":
        papers = payload.get("papers", [])

    elif tool_name == "get_abstract":
        papers = [payload.get("paper", payload)]

    else:
        return []

    if not isinstance(papers, list):
        raise TypeError("arXiv papers 必须是列表")

    hits = []

    for paper in papers[:10]:
        if not isinstance(paper, dict):
            continue

        raw_id = (
            paper.get("id")
            or paper.get("paper_id")
            or paper.get("arxiv_id")
            or (
                arguments.get("paper_id")
                if tool_name == "get_abstract"
                else None
            )
        )

        match = ARXIV_ID.search(str(raw_id or ""))
        if not match:
            continue

        paper_id = match.group(1)
        title = str(paper.get("title") or "").strip()

        authors = paper.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        if not isinstance(authors, list):
            authors = []

        authors = [
            str(a.get("name", "") if isinstance(a, dict) else a).strip()
            for a in authors[:50]
        ]
        authors = [a for a in authors if a]

        abstract = str(
            paper.get("abstract") or paper.get("summary") or ""
        ).strip()

        if not title and not authors and not abstract:
            continue

        url = f"https://arxiv.org/abs/{paper_id}"

        content = (
            f"Title: {title}\n"
            f"Authors: {', '.join(authors) or 'not provided'}\n"
            f"Published: {paper.get('published') or 'not provided'}\n"
            f"Abstract: {abstract[:3000]}\n"
            f"Source URL: {url}"
        )

        hits.append({
            "chunk_id": f"arxiv:{paper_id}",
            "content": content,
            "source": f"arXiv:{paper_id} | {title}",
            "page": None,
            "source_url": url,
            "provider": "mcp:arxiv",
            "score_type": "unscored_external",
            "evidence_type": "paper_metadata",
        })

    return hits
