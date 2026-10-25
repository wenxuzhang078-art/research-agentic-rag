"""使用 PyMuPDF 按页读取 PDF 文本和来源信息。"""
from pathlib import Path
import pymupdf


def load_pdf(pdf_path: Path) -> list[dict]:
    with pymupdf.open(pdf_path) as pdf:
        return [
            {"source": pdf_path.name, "page": i, "content": page.get_text("text")}
            for i, page in enumerate(pdf, start=1)
        ]
