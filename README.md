# MVC Research Agent

面向 **MVC（Multi-view Clustering，多视图聚类）** 论文的私有知识库问答 Agent。将英文 PDF 解析、分块并写入 Milvus，通过中文问题检索论文证据，生成带来源引用的回答。提供命令行、FastAPI 和 React 网页，三者共用同一套检索与 Agent 实现。

网页中的产品名为 **Research Atlas**。

## 功能

| 功能 | 当前实现 |
| --- | --- |
| PDF 入库 | PyMuPDF 按页提取文本，800 字符分块、100 字符重叠，生成 1024 维向量 |
| 基础 RAG | Dense + BM25 → RRF 融合 → Qwen Rerank → 带引用回答 |
| Agentic RAG | LangGraph 的 Plan → Act → Grade → Replan → Generate；Act 内含有界 ReAct 工具循环 |
| 本地工具 | `rag_search` 完整检索、`read_chunk` 按已知 ID 读取原文 |
| 外部文献 | 可选 stdio MCP，内置 arXiv 搜索与摘要证据适配 |
| 网页 | RAG / Agent 模式切换、引用片段、节点轨迹、PDF 上传与本地文件列表 |
| 验证 | 无真实模型调用的单元测试，以及需要真实服务的检索评测 |

PDF 和向量库保存在本地；**模型推理使用云端 API**，入库文本、问题及相关证据会发送给配置的 Embedding、Chat 或 Rerank 服务。启用 arXiv MCP 后，相关查询也会发送到外部文献服务。

## 环境要求

- Python **3.12**。
- Docker Engine / Docker Desktop，包含 Docker Compose v2，用于运行 Milvus、etcd、MinIO。
- Node.js **22.12+** 和 npm，仅使用或构建网页时需要。
- 可调用 Chat、Embedding 和 Rerank 的百炼 API 配置。
- 可选：`uv` / `uvx`，用于运行仓库提供的 arXiv MCP 配置。

以下命令以 **Windows PowerShell** 为例，除注明外都在项目根目录执行。macOS / Linux 创建虚拟环境后使用 `source .venv/bin/activate`，复制配置使用 `cp .env.example .env`，其他 Python、npm、Docker 命令相同。

## 快速开始

### 1. 安装与配置

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-api.txt
Copy-Item .env.example .env
```

`requirements-api.txt` 已包含核心依赖。仅使用 CLI 时可改为安装 `requirements.txt`。已有 `.env` 时保留原文件，勿重复覆盖；真实密钥不应写入源码。

编辑 `.env`，至少设置：

| 变量 | 用途 |
| --- | --- |
| `DASHSCOPE_API_KEY` | 模型 API Key |
| `DASHSCOPE_BASE_URL` | Chat / Embedding 的 OpenAI 兼容地址，示例文件提供默认值 |
| `MODEL_NAME` | Chat 模型，默认 `qwen-plus`，Agent 使用其工具调用能力 |
| `EMBEDDING_MODEL` | 默认 `text-embedding-v4`，返回维度必须为 1024 |
| `RERANK_BASE_URL` | **正常本地问答必填**，需填写业务空间可访问的 Rerank 兼容基础地址 |
| `RERANK_MODEL` | 默认 `qwen3-rerank` |
| `MILVUS_URI` | 默认 `http://127.0.0.1:19531`，与 Compose 映射一致 |
| `MILVUS_COLLECTION` | 默认 `mvc_hybrid_1024`，初始化、入库、检索必须一致 |

Rerank 是当前 RAG 和 Agent 本地检索的固定步骤。`RERANK_BASE_URL` 填基础地址，代码会追加 `/reranks`，不要填写完整请求路径，也不要直接照抄 Chat 地址。请按实际地域和业务空间核对[百炼重排序文档](https://help.aliyun.com/zh/model-studio/rerank)。

其他可选配置见 [.env.example](.env.example)。环境变量优先于 `.env`；修改配置后重新启动 CLI / API 进程。

### 2. 启动并初始化 Milvus

```powershell
docker compose up -d
docker compose ps
```

等待 `milvus` 显示健康状态，再执行：

```powershell
python -m scripts.init_milvus
```

该命令创建或检查 Hybrid Collection 和索引。重复执行不会清空数据；已有集合仍须满足当前 Schema。服务端口为 `127.0.0.1:19531`，Milvus 健康检查端口为 `127.0.0.1:9092`。

### 3. 导入论文

将有文本层的英文 PDF 放入 `data/papers/`，替换示例文件名后执行：

```powershell
python -m scripts.ingest_pdf "data/papers/your-paper.pdf"
```

也可以启动网页后上传 PDF。项目不附带私有论文或向量数据，新环境需要自行导入；保留原 Docker 数据卷和集合配置的现有环境可继续使用原数据。

### 4. 运行命令行问答

```powershell
python -m main rag --top-k 5
python -m main agent --show-steps
```

启动后会提示输入一个问题，回答完成后退出。`rag` 直接使用固定检索流水线；`agent` 还会进行规划、工具补检和证据审核。

**启用 MCP 的 CLI 命令：**

```powershell
python -m pip install -r requirements-mcp.txt
python -m pip install uv
python -m main agent --mcp-config configs/mcp_arxiv.json --show-steps
```

`-m` 后写模块名 `main`，不写 `main.py`；也可等价运行 `python main.py agent ...`。`--mcp-config` 属于 `agent` 子命令，放在 `agent` 后面，不额外插入 `--`。旧文档中的 `--retriever` 已不再适用。

MCP 安装、注册验证与日志定位见 [MCP 接入](docs/MCP.md)；IDE 参数与命令行调试见 [开发指南](docs/DEVELOPMENT.md)。

### 5. 启动网页

终端 A，在根目录启用虚拟环境后启动后端：

```powershell
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

终端 B：

```powershell
cd frontend
npm ci
npm run dev
```

打开 [Research Atlas](http://127.0.0.1:5173)，接口文档位于 [Swagger UI](http://127.0.0.1:8000/docs)。

**网页后端启用 MCP** 使用环境变量，而不是 CLI 参数。在终端 A 启动前执行：

```powershell
$env:MCP_CONFIG_PATH = "configs/mcp_arxiv.json"
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

也可在根目录 `.env` 中设置 `MCP_CONFIG_PATH=configs/mcp_arxiv.json`。详情见 [Web 运行与 API 指南](docs/WEB_QUICKSTART.md)。

## 构建后由后端提供网页

```powershell
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

构建完成后重新启动 API，访问[本机网页](http://127.0.0.1:8000/)，无需另开 Vite。Compose 仅启动数据库基础设施，不会自动启动 Python 后端或前端。

## 测试与检索评测

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

单元测试使用模拟结果和临时文件，不需要 API Key、Milvus 或真实 MCP Server。真实检索评测另行运行：

```powershell
python -m evals.evaluate_retrieval
python -m evals.evaluate_retrieval --with-rerank
```

评测会访问模型 API 和 Milvus。标注集中的 Chunk ID 对应特定论文文件名、页码和分块规则；换成自己的论文后须同步更新 `evals/retrieval_cases.json`。详见[开发与发布说明](docs/DEVELOPMENT.md)。

## 使用边界

- 每个 CLI / HTTP 问题独立执行，没有多轮记忆或会话持久化。网页历史保存在当前页面内存，刷新后清空。
- HTTP 问答一次性返回，没有 Token 流式输出。上传在请求内等待解析、Embedding 和写库完成，默认上限 20 MB。
- 文献列表展示 `data/papers/` 中的 PDF 文件，不是 Milvus 全量文档目录；没有文档删除、版本管理或 OCR。
- CLI 按文件名生成 Chunk ID，同名文件可能覆盖已有片段；网页上传使用带随机后缀的文件名，同一 PDF 重复上传会形成多份记录。
- 当前面向本机单用户使用，没有账号鉴权、速率限制或后台任务队列。Compose 中的 MinIO 凭据用于本地演示。
- `docker compose stop` 可暂停服务并保留数据；`docker compose down` 默认保留命名卷，`docker compose down -v` 会删除数据卷。

## 文档导航

- [架构与数据流](docs/ARCHITECTURE.md)：RAG、外层 Graph、内层 ReAct、证据规则。
- [MCP 接入](docs/MCP.md)：配置格式、CLI / Web 启用方式、arXiv 适配与排错。
- [Web 与 API](docs/WEB_QUICKSTART.md)：启动、接口契约、构建与常见问题。
- [前端说明](frontend/README.md)：开发、代理、目录与页面行为。
- [开发与发布](docs/DEVELOPMENT.md)：调试参数、测试、评测及 GitHub 提交准备。
