# 架构与数据流

## 项目结构

```text
mvc-research-agent/
├── main.py                   # CLI：rag / agent
├── src/
│   ├── agent/                # 外层 Graph、内层 ReAct、State、Prompt 与证据上下文
│   │   ├── graph.py          # Plan / Act / Grade / Replan / Generate 及有界路由
│   │   ├── react.py          # 原生 Function Calling 与工具反馈循环
│   │   ├── context.py        # Grade 证据去重、字符裁剪与编号
│   │   └── nodes/            # 五个节点的实现
│   ├── tools/                # ToolRegistry、rag_search、read_chunk
│   ├── integrations/         # stdio MCP Client、arXiv Evidence Adapter
│   ├── ingest/               # PDF 按页解析、字符分块、入库编排
│   ├── embedding/            # Qwen Embedding，固定 1024 维
│   ├── storage/              # Milvus 连接、Schema、索引及 upsert
│   ├── retrieval/            # Dense、BM25、RRF、查询翻译、Rerank
│   ├── rag/                  # 统一检索门面与带引用答案生成
│   └── api/                  # FastAPI 问答、状态、PDF 上传与静态前端
├── frontend/                 # React + TypeScript + Vite 网页
├── configs/mcp_arxiv.json    # 固定版本的 arXiv MCP 白名单配置
├── scripts/                  # 初始化 Collection、导入 PDF
├── tests/                    # 不依赖真实外部服务的测试
├── evals/                    # 检索标注集与真实服务评测
├── data/papers/              # 本地论文，默认不提交
├── logs/                     # MCP 子进程诊断日志，默认不提交
├── docs/                     # 运行、架构、MCP、开发说明
├── docker-compose.yml        # Milvus / etcd / MinIO；不包含应用进程
├── requirements*.txt         # 核心 / API / MCP / 开发依赖
└── .env.example              # 无真实密钥的配置模板
```

## PDF 入库

`scripts.ingest_pdf` 和 HTTP 上传共用 `src.ingest.service.ingest_pdf`：

```text
PDF → PyMuPDF 逐页文本 → 页内字符分块 → 1024 维 Embedding → Milvus upsert
```

- 页码从 1 开始，每页 Chunk 下标从 0 开始，默认分块 800 字符、重叠 100 字符。
- 主键形如 `paper.pdf_p1_c0`；`document_id` 等于保存的文件名，`version_id` 固定为 1。
- 所有记录写入同一 `MILVUS_COLLECTION`，`kb_name` 固定为 `mvc_research`。
- Schema 包含 Dense 向量 `embedding`、原文 `content`、BM25 稀疏向量 `content_sparse` 及来源字段。BM25 使用 Milvus 英文分析器和内置函数生成。
- Dense 索引为 `AUTOINDEX / COSINE`，稀疏索引为 `SPARSE_INVERTED_INDEX / BM25`。

目前不进行 OCR、表格结构还原或文件内容级去重。CLI 导入同名文件会复用主键；若新内容分块数减少，upsert 不会自动删除旧的多余片段。网页上传为文件名添加随机后缀，重复上传会生成独立记录。

## 统一 RAG 流程

CLI、HTTP 和 Agent 本地工具都使用 `src.rag.service`：

```text
问题 ───────────────────────→ Dense（原问题 Embedding） ─┐
  └→ 中文问题忠实翻译为英文 → BM25（英文查询） ──────────┤
                                                       ↓
                                     Milvus RRF(k=60) 融合
                                                       ↓
                                      Qwen Rerank → Top K
                                                       ↓
                                    来源编号 + 证据 → Chat 回答
```

没有中文字符时，BM25 直接使用原问题。默认每路召回 20 条，再融合候选并精排。普通 RAG 默认返回 5 条，允许 1–20 条，不经过 Plan / ReAct / Grade。

`RERANK_BASE_URL` 是固定流水线的必要配置。底层 Dense / Hybrid 函数仍供评测比较，但不作为当前 CLI 的可选 `--retriever`。

## 外层 Graph 与内层 ReAct

```text
Plan → Act → Grade ──充分────────────────────→ Generate
              │
              └─不足且未满两轮 → Replan → Act → Grade → Generate
```

1. **Plan**：模型输出 JSON 检索式与理由；失败时回退到原问题。
2. **Act**：先固定调用 `rag_search(top_k=8)` 预取，再由内层 ReAct 根据证据决定是否补检。每轮 Act 的内层最多两轮工具请求、累计四次工具执行；该预算不含固定预取。
3. **Grade**：先按 Rerank 分数预筛，默认门槛 0.20；再由模型选择直接相关证据并判断是否覆盖问题。没有候选时跳过模型审核。
4. **Replan**：根据缺失方面生成新检索式；外层最多执行两轮 Act。
5. **Generate**：无相关证据时说明不足；只有部分证据时回答已知部分并列出缺项；证据充分时生成完整回答。统一引用 `relevant_hits`。

内层 ReAct 使用 Qwen 原生 `tool_calls`，将执行结果作为 `role=tool` 消息回传。ToolRegistry 负责 JSON Schema 校验、执行和统一结果；模型不能直接执行任意 Python 或命令。

工具执行失败会记录到轨迹并允许补检。最终没有可用证据时可能返回正常 HTTP 响应和证据不足说明；检查 `steps` 中的工具错误，不能仅凭 HTTP 200 判断检索成功。

## 工具与 MCP

默认工具只有 `rag_search` 和 `read_chunk`。显式启用 MCP 后，白名单远端工具以 `mcp_<server_id>_<tool_name>` 注册到当前 Python 进程。

Function Calling 决定工具和参数；Registry 校验并调用；MCP 承担外部进程协议通信。arXiv 适配器将标题、作者、摘要和 URL 转换为证据，其类型为 `paper_metadata`，不代表下载或索引了论文全文。配置与通用返回格式见 [MCP 接入](MCP.md)。

## 证据、分数与状态

- 本地证据携带 `chunk_id`、`source`、`page`、`content`；外部文献可用 `source_url` 替代页码。
- `rerank_relevance` 可用于 Grade 门槛；RRF、COSINE、BM25 分数尺度不同，不与该门槛混用。`unscored_read`、`unscored_external` 由语义审核处理。
- Grade 的上下文最多 12 条、合计约 14000 字符、单条最多 1200 字符；超量时兼顾前部排名和尾部新证据。这是字符预算，没有 Token 计量。
- Graph 没有 Checkpointer 或跨请求 Memory。每次 CLI / HTTP 请求创建新 State；网页历史仅供当前页面展示。
- FastAPI 将同步 RAG 与入库放到线程执行；上传锁仅覆盖单个进程，没有持久化任务队列。MCP 注册表也仅在当前进程内有效。

运行方式见[项目 README](../README.md)，HTTP 契约见 [Web 指南](WEB_QUICKSTART.md)。
