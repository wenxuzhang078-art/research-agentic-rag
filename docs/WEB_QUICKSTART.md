# Web 运行与 API 指南

网页和 CLI 共用 `src.rag.service`、`src.agent.graph` 以及同一个 Milvus Collection。首次使用先按[根目录 README](../README.md) 配置模型、启动 Milvus 并导入论文。

## 开发模式

终端 A，在项目根目录运行：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-api.txt
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

终端 B：

```powershell
cd frontend
npm ci
npm run dev
```

需要 Node.js 22.12+。访问[网页](http://127.0.0.1:5173)；Vite 代理 `/api` 和 `/health` 到 8000 端口，API 文档位于 [Swagger UI](http://127.0.0.1:8000/docs)。

后端启用 MCP 的方式是启动前设置 `$env:MCP_CONFIG_PATH = "configs/mcp_arxiv.json"`，或在根目录 `.env` 填写该变量。不能向 Uvicorn 传 `--mcp-config`；该参数只属于 `main agent`。依赖安装、验证和关闭方法见 [MCP 指南](MCP.md)。

## 构建演示

在 `frontend/` 执行 `npm run build`，然后在根目录重新启动 API：

```powershell
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)。API 在导入时决定是否挂载构建资源，因此首次构建后需重启。未构建时 `/` 显示 API 提示页，不影响接口运行。

当前面向本机单用户使用，没有账号鉴权、请求限速或持久化任务队列；保持绑定 `127.0.0.1`。Compose 只运行数据库基础设施。

## 接口总览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health`、`/api/health` | API 进程健康检查，不主动连接 Milvus / 模型 |
| GET | `/api/status` | MCP 注册状态、工具名、PDF 大小限制、会话记忆标记 |
| POST | `/api/chat` | 单轮 RAG 或 Agent 问答 |
| GET | `/api/documents` | 服务器 `data/papers/` 下的 PDF 文件 |
| POST | `/api/documents/upload` | multipart 上传 PDF，解析、Embedding、入库 |
| GET | `/docs` | 交互式 OpenAPI 文档 |

### 问答请求

`POST /api/chat`，JSON 请求体：

```json
{
  "question": "该方法如何处理不同视图之间的一致性？",
  "mode": "agent",
  "top_k": 5,
  "show_steps": true
}
```

| 字段 | 约束与语义 |
| --- | --- |
| `question` | 必填，1–2000 字符，拒绝纯空白 |
| `mode` | `rag` 或 `agent`，默认 `agent` |
| `top_k` | 1–20，默认 5；只控制 `rag` 模式，Agent 固定预取 8 条并自行补检 |
| `show_steps` | 默认 `true`；只控制 Agent 是否返回轨迹，不影响实际执行 |

PowerShell 示例：

```powershell
$chatBody = @{
    question = "该方法如何处理不同视图之间的一致性？"
    mode = "agent"
    show_steps = $true
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/chat -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($chatBody))
```

返回字段：

| 字段 | 含义 |
| --- | --- |
| `request_id`、`mode`、`answer` | 请求标识、执行模式、回答正文 |
| `sources` | 证据数组，含编号、Chunk ID、来源、页码 / URL、片段及相关度类型 |
| `steps` | Agent 节点轨迹；普通 RAG 或 `show_steps=false` 时为空 |
| `attempts` | Agent 的 Act 轮数，最多 2；普通 RAG 为 0 |
| `sufficient` | Agent 的证据充分性判断；普通 RAG 仅表示是否返回来源 |
| `prefilter_stats` | Agent 的分数预筛统计；普通 RAG 为空对象 |
| `duration_ms` | 请求处理耗时，毫秒 |

外部文献来源可以 `page=null`、`score=null`，通过 `source_url` 定位。Agent 的 `sufficient=false` 时仍可能有部分回答和对应来源，不能将其等同于 `sources` 必为空。

参数不合法返回 422；未被流程内部处理的问答异常返回 502。工具失败也可能被 Agent 记录并转成证据不足回答，应结合 `steps` 和后端日志判断。

### PDF 上传

`POST /api/documents/upload` 使用 multipart 字段 `file`，不接收本机文件路径字符串。可在 Swagger 或网页中操作，也可执行：

```powershell
curl.exe -F "file=@data/papers/your-paper.pdf" http://127.0.0.1:8000/api/documents/upload
```

默认上限 20 MB，通过 `.env` 中的 `MAX_PDF_MB` 调整后重启后端。接口检查 `.pdf` 后缀和 `%PDF-` 文件头，保存时规范化文件名并追加随机后缀。

成功响应中，`result` 为 JSON 对象，包含 `pdf`、`pages`、`chunks`、`collection`、`upsert`；顶层同时返回 `original_filename` 和 `saved_filename`。网页读取 `result.pages` 和 `result.chunks` 展示入库结果。

空文件 / 非 PDF 返回 400，超限返回 413，解析或写库异常返回 502。失败时会清理保存的 PDF；这不构成跨模型服务与 Milvus 的事务回滚。当前没有请求取消后的任务管理或自动重试队列。

`GET /api/documents` 返回 `documents` 和范围说明 `note`。每项含 `filename`、`size_bytes`、UTC ISO 格式的 `modified_at`。该列表不检查文件是否已成功入库，也不包含仅存在于旧 Milvus 数据中的论文。

## 排错

| 现象 | 检查项 |
| --- | --- |
| 网页显示服务未连接 | 后端是否运行在 8000；Vite 代理是否一致；访问 `/health` |
| 健康检查成功但问答失败 | Milvus 是否健康、Collection 是否初始化、模型 Key / 地址 / 权限是否正确 |
| 提示配置 `RERANK_BASE_URL` | Rerank 是固定本地检索步骤；填写当前空间可访问的兼容基础地址 |
| 上传后无文本 | PDF 是否有文本层；扫描件当前没有 OCR |
| 页面等待较久 | 问答含多次模型与工具调用，上传等待 Embedding 和写库；查看 API 日志及 MCP stderr |
| 前端参数变化无效 | `top_k` 仅作用于普通 RAG；MCP 配置和密钥只在后端设置 |
| 8000 上没有网页资源 | 先完成 `npm run build`，再重新启动 API |
| 文献条数与检索来源不一致 | 文件列表与 Milvus 数据不是同一统计范围，网页重复上传还会保存新文件名 |

页面历史只存在内存中；每次 HTTP 问答是独立 State。当前没有 Token 流式输出，回答完成后一次性返回。
