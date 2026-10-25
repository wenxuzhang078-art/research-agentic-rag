"""运行：python -m scripts.ingest_pdf "data/papers/example.pdf""" 
import argparse
from src.ingest.service import ingest_pdf

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="写入 MVC 论文到 Milvus Hybrid Collection")
    parser.add_argument("pdf", help="PDF 路径")
    args = parser.parse_args()
    print(ingest_pdf(args.pdf))
