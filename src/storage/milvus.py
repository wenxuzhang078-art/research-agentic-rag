"""唯一的 Milvus 连接配置；复用原 Docker 19531 端口。"""
from __future__ import annotations

import os
from dotenv import load_dotenv
from pymilvus import MilvusClient

load_dotenv()


def connect_milvus() -> MilvusClient:
    return MilvusClient(uri=os.getenv("MILVUS_URI", "http://127.0.0.1:19531"))
