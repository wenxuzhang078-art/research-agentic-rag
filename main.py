"""主入口：python -m main rag / python -m main agent。"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MVC 科研论文 RAG / LangGraph Agent")
    sub = parser.add_subparsers(dest="mode", required=True)
    rag = sub.add_parser("rag", help="固定的 Dense+BM25→RRF→Rerank→Answer")
    rag.add_argument("--top-k", type=int, default=5, help="返回片段数，1–20，默认 5")
    agent = sub.add_parser("agent", help="Plan → Act → Grade → Replan → Generate")
    agent.add_argument("--show-steps", action="store_true", help="显示节点轨迹")
    agent.add_argument("--mcp-config", type=Path, help="可选：可信任的本地 MCP Server JSON 配置")
    return parser


def print_sources(hits: list[dict]) -> None:
    print("\n【参考来源】")
    for i, hit in enumerate(hits, 1):
        page = hit.get("page")
        locator = f"第{page}页" if type(page) is int else (hit.get("source_url") or "来源位置未提供")
        print(f"[{i}] {hit.get('source')} {locator} {hit.get('chunk_id', '')}")


async def run_agent(args, question: str) -> None:
    if args.mcp_config is not None:
        from src.integrations.mcp_client import register_stdio_mcp
        cfg = json.loads(args.mcp_config.read_text(encoding="utf-8"))
        names = await register_stdio_mcp(
            server_id=cfg["server_id"], command=cfg["command"],
            args=cfg.get("args", []), allowed_tools=set(cfg["allowed_tools"]),
        )
        print("已注册 MCP 工具：", names)
    from src.agent.graph import graph
    result = await graph.ainvoke(
        {"question": question, "attempts": 0, "steps": [], "hits": []},
        config={"recursion_limit": 15},
    )
    print("\n【回答】\n", result.get("answer", ""))
    if args.show_steps:
        print("\n【执行轨迹】")
        for step in result.get("steps", []):
            print(json.dumps(step, ensure_ascii=False))
        print("【执行轮数】", result.get("attempts", 0))
        print("【证据充分】", result.get("sufficient", False))
        print("【分数预筛】", result.get("prefilter_stats", {}))
    print_sources(result.get("relevant_hits", []))


def run_rag(args, question: str) -> None:
    from src.rag.service import ask_rag
    result = ask_rag(question, top_k=args.top_k)
    print("\n【回答】\n", result["answer"])
    print_sources(result["sources"])


def main():
    args = create_parser().parse_args()
    question = input("请输入 MVC 科研问题：").strip()
    if not question:
        raise SystemExit("问题不能为空")
    if args.mode == "agent":
        asyncio.run(run_agent(args, question))
    else:
        run_rag(args, question)


if __name__ == "__main__":
    main()
