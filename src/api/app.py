"""MVC Research Agent 的 HTTP 入口。

与 CLI 共用 src.rag.service.ask_rag 和 src.agent.graph.graph。
仅适合本机学习/单用户使用；部署到公网前必须加身份认证、速率限制及持久化任务队列。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
FRONTEND_DIST = ROOT / "frontend" / "dist"
PAPERS_DIR = ROOT / "data" / "papers"
MAX_UPLOAD_BYTES = int(os.getenv("MAX_PDF_MB", "20")) * 1024 * 1024
UPLOAD_LOCK = asyncio.Lock()
log = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["rag", "agent"] = "agent"
    top_k: int = Field(default=5, ge=1, le=20)
    show_steps: bool = True


class Source(BaseModel):
    index: int
    chunk_id: str | None = None
    source: str
    page: int | None = None
    source_url: str | None = None
    content: str = ""
    score: float | None = None
    score_type: str | None = None
    provider: str | None = None


class ChatResponse(BaseModel):
    request_id: str
    mode: Literal["rag", "agent"]
    answer: str
    sources: list[Source]
    steps: list[dict[str, Any]] = Field(default_factory=list)
    attempts: int = 0
    sufficient: bool | None = None
    prefilter_stats: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int


def _normalize_sources(hits: list[dict[str, Any]]) -> list[Source]:
    """API 证据模型同时支持本地 PDF 页码及外部 arXiv URL。"""
    results = []
    for n, item in enumerate(hits, start=1):
        score = item.get("rerank_score")
        if score is None and item.get("score_type") == "rerank_relevance":
            score = item.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        page = item.get("page")
        results.append(Source(
            index=n,
            chunk_id=str(item["chunk_id"]) if item.get("chunk_id") is not None else None,
            source=str(item.get("source") or "未知来源"),
            page=page if type(page) is int else None,
            source_url=str(item["source_url"]) if item.get("source_url") else None,
            content=str(item.get("content") or "")[:5000],
            score=score,
            score_type=item.get("score_type"),
            provider=item.get("provider"),
        ))
    return results


def _run_rag_sync(question: str, top_k: int) -> dict[str, Any]:
    from src.rag.service import ask_rag
    return ask_rag(question, top_k=top_k)


async def _run_agent(question: str) -> dict[str, Any]:
    # 延迟导入：没有启动 LangGraph 时也能检查 FastAPI 健康状态。
    from src.agent.graph import graph
    return await graph.ainvoke(
        {"question": question, "attempts": 0, "steps": [], "hits": []},
        config={"recursion_limit": 15},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """如用户配置了受信任的 MCP Server，则在 API 启动时注册一次。"""
    app.state.mcp_tools = []
    app.state.mcp_status = "disabled"
    config_path = os.getenv("MCP_CONFIG_PATH", "").strip()
    print(f"[MCP] 当前配置路径：{config_path!r}", flush=True)
    if config_path:
        try:
            config = json.loads(Path(config_path).resolve().read_text(encoding="utf-8"))
            from src.integrations.mcp_client import register_stdio_mcp
            tools = await register_stdio_mcp(
                server_id=config["server_id"],
                command=config["command"],
                args=config.get("args", []),
                allowed_tools=set(config["allowed_tools"]),
            )
            app.state.mcp_tools = tools
            app.state.mcp_status = "connected"
            log.info("注册 MCP 工具：%s", tools)
        except Exception:
            app.state.mcp_status = "error"
            log.exception("MCP 初始化失败；本地 RAG/Agent 仍可使用")
    yield


app = FastAPI(
    title="MVC Research Agent API", version="1.0.0", lifespan=lifespan,
    description="本机科研论文 RAG、LangGraph Agent 及 PDF 入库 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "mvc-research-agent"}


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "MVC Research Agent", "version": "1.0.0"}


@app.get("/api/status")
def status():
    return {
        "service": "MVC Research Agent",
        "mcp_status": getattr(app.state, "mcp_status", "disabled"),
        "mcp_tools": getattr(app.state, "mcp_tools", []),
        "max_pdf_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "session_memory": False,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(422, detail="问题不能为空")
    started = perf_counter()
    try:
        if request.mode == "rag":
            result = await asyncio.to_thread(_run_rag_sync, question, request.top_k)
            sources = _normalize_sources(result.get("sources", []))
            return ChatResponse(
                request_id=uuid4().hex,
                mode="rag", answer=result.get("answer", ""),
                sources=sources,
                sufficient=bool(sources),
                duration_ms=round((perf_counter() - started) * 1000),
            )
        result = await _run_agent(question)
        sufficient = bool(result.get("sufficient", False))
        relevant = result.get("relevant_hits", [])
        return ChatResponse(
            request_id=uuid4().hex,
            mode="agent", answer=result.get("answer", ""),
            sources=_normalize_sources(relevant),
            steps=result.get("steps", []) if request.show_steps else [],
            attempts=int(result.get("attempts", 0)),
            sufficient=sufficient,
            prefilter_stats=result.get("prefilter_stats", {}),
            duration_ms=round((perf_counter() - started) * 1000),
        )
    except Exception as exc:
        log.exception("问答失败 mode=%s", request.mode)
        raise HTTPException(
            status_code=502,
            detail=f"问答失败（{type(exc).__name__}）。请检查 API 终端日志、Milvus 与模型配置。",
        ) from exc


@app.get("/api/documents")
def documents():
    """仅列出当前服务器上存放的 PDF；不代表 Milvus 全量文档清单。"""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in PAPERS_DIR.glob("*.pdf"):
        if not item.is_file():
            continue
        stat = item.stat()
        rows.append({
            "filename": item.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    rows.sort(key=lambda d: d["modified_at"], reverse=True)
    return {"documents": rows, "note": "列表仅表示服务器上的 PDF 文件，并非 Milvus Collection 的全部记录。"}


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """限制 PDF 大小及类型，使用安全文件名，落盘后复用既有入库函数。"""
    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="仅支持 PDF 文件")
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(filename).stem).strip("-")[:70] or "paper"
    destination = PAPERS_DIR / f"{safe_stem}-{uuid4().hex[:12]}.pdf"
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    async with UPLOAD_LOCK:
        total = 0
        try:
            with destination.open("xb") as stream:
                while data := await file.read(1024 * 1024):
                    total += len(data)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, detail=f"文件不能超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
                    if total == len(data) and not data.startswith(b"%PDF-"):
                        raise HTTPException(400, detail="文件内容不是有效的 PDF 格式")
                    stream.write(data)
            if total == 0:
                raise HTTPException(400, detail="文件为空")
            from src.ingest.service import ingest_pdf
            result = await asyncio.to_thread(ingest_pdf, destination)
            return {"original_filename": filename, "saved_filename": destination.name, "result": str(result)}
        except HTTPException:
            destination.unlink(missing_ok=True)
            raise
        except Exception as exc:
            destination.unlink(missing_ok=True)
            log.exception("PDF 入库失败")
            raise HTTPException(502, detail=f"PDF 入库失败（{type(exc).__name__}）。请检查后端日志。") from exc
        finally:
            await file.close()


# 生产构建后用同一 FastAPI 进程提供前端静态页面；开发环境由 Vite 代理 /api。
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/", response_class=HTMLResponse)
def index():
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return HTMLResponse(
        "<html><meta charset='utf-8'><body style='font-family:system-ui;padding:50px'>"
        "<h2>MVC Research Agent API 已启动</h2>"
        "<p>前端尚未构建：请进入 frontend/ 执行 npm install && npm run dev，"
        "然后访问 http://localhost:5173。</p>"
        "<p>API 文档：<a href='/docs'>/docs</a></p></body></html>"
    )
