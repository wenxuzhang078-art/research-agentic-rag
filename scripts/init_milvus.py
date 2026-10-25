"""首次使用时运行：python -m scripts.init_milvus"""
from src.storage.schema import ensure_collection

if __name__ == "__main__":
    ensure_collection()
