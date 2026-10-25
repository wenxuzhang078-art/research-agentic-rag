"""PDF → 文本页 → Chunk → 1024维向量 → Hybrid Collection。"""
from __future__ import annotations

from pathlib import Path

from src.ingest.loader import load_pdf
from src.ingest.chunker import split_documents
from src.embedding.service import embed_texts
from src.storage.milvus import connect_milvus
from src.storage.schema import COLLECTION_NAME
from src.storage.writer import upsert_chunks


def ingest_pdf(path: str | Path) -> dict:
    pdf_path = Path(path).expanduser().resolve()
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise FileNotFoundError(f"PDF 文件不存在：{pdf_path}")
    pages = load_pdf(pdf_path)
    chunks = split_documents(pages, chunk_size=800, chunk_overlap=100)
    if not chunks:
        raise ValueError("PDF 没有可入库的文本")
    embeddings = embed_texts([c["content"] for c in chunks])
    client = connect_milvus()
    try:
        if not client.has_collection(COLLECTION_NAME):
            raise RuntimeError("Milvus Collection 尚未创建，请先执行 python -m scripts.init_milvus")
        result = upsert_chunks(client, chunks, embeddings)
    finally:
        client.close()
    return {"pdf": pdf_path.name, "pages": len(pages), "chunks": len(chunks), "collection": COLLECTION_NAME, "upsert": result}
