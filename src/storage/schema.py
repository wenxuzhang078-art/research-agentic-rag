import os


from pymilvus import (
    CollectionSchema,
    FieldSchema,
    DataType,
    Function,
    FunctionType
)

from src.storage.milvus import connect_milvus

COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "mvc_hybrid_1024")



def create_hybrid_schema() -> CollectionSchema:
    fields = [
        FieldSchema(
            name="chunk_id",
            dtype=DataType.VARCHAR,
            is_primary=True,
            max_length=255
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=1024
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            enable_analyzer=True,
            analyzer_params={"type": "english"}
        ),
        FieldSchema(
            name="content_sparse",
            dtype=DataType.SPARSE_FLOAT_VECTOR
        ),
        FieldSchema(
            name="kb_name",
            dtype=DataType.VARCHAR,
            max_length=64
        ),
        FieldSchema(
            name="document_id",
            dtype=DataType.VARCHAR,
            max_length=255
        ),
        FieldSchema(
            name="version_id",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="chunk_index",
            dtype=DataType.INT64
        ),
        FieldSchema(
            name="source",
            dtype=DataType.VARCHAR,
            max_length=512
        ),
        FieldSchema(
            name="page",
            dtype=DataType.INT64
        )
    ]

    bm25_function = Function(
        name="content_bm25",
        function_type=FunctionType.BM25,
        input_field_names=["content"],
        output_field_names=["content_sparse"]
    )

    return CollectionSchema(
        fields=fields,
        functions=[bm25_function],
        enable_dynamic_field=False
    )


def ensure_collection():
    client = connect_milvus()

    try:
        # 1. 创建新 Collection
        if not client.has_collection(COLLECTION_NAME):
            schema = create_hybrid_schema()

            client.create_collection(
                collection_name=COLLECTION_NAME,
                schema=schema
            )

            print("Hybrid Collection 创建成功")
        else:
            print("Hybrid Collection 已存在")

        # 2. 检查 Schema
        description = client.describe_collection(
            collection_name=COLLECTION_NAME
        )

        field_names = {
            field["name"]
            for field in description["fields"]
        }

        if "content_sparse" not in field_names:
            raise RuntimeError("缺少 content_sparse 字段")

        if not description.get("functions"):
            raise RuntimeError("Collection 缺少 BM25 Function")

        # 3. 检查已有索引
        existing_indexes = set(
            client.list_indexes(
                collection_name=COLLECTION_NAME
            )
        )

        index_params = client.prepare_index_params()
        need_create_index = False

        # Dense 索引
        if "idx_embedding" not in existing_indexes:
            index_params.add_index(
                field_name="embedding",
                index_name="idx_embedding",
                index_type="AUTOINDEX",
                metric_type="COSINE"
            )
            need_create_index = True

        # BM25 稀疏索引
        if "idx_content_sparse" not in existing_indexes:
            index_params.add_index(
                field_name="content_sparse",
                index_name="idx_content_sparse",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="BM25",
                params={
                    "inverted_index_algo": "DAAT_MAXSCORE"
                }
            )
            need_create_index = True

        if need_create_index:
            client.create_index(
                collection_name=COLLECTION_NAME,
                index_params=index_params
            )

        # 4. 加载 Collection
        client.load_collection(
            collection_name=COLLECTION_NAME
        )

        print("Collection:", COLLECTION_NAME)
        print(
            "索引：",
            client.list_indexes(
                collection_name=COLLECTION_NAME
            )
        )

        print("Hybrid Collection 准备完成")

    finally:
        client.close()
