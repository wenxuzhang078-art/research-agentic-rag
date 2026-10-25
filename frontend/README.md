# Research Atlas 前端

MVC Research Agent 的 React + TypeScript + Vite 网页，支持普通 RAG / Agent 问答、Markdown 与数学公式、引用片段、执行轨迹、PDF 上传和本地文献文件列表。

后端、模型和 Milvus 的初始化见[根目录 README](../README.md)。前端不保存 API Key，也不直接连接 Milvus 或启动 MCP。

## 本地开发

需要 Node.js **22.12+**。先在项目根目录启动 FastAPI：

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

再打开一个终端，在 `frontend/` 执行：

```powershell
npm ci
npm run dev
```

访问 [http://127.0.0.1:5173](http://127.0.0.1:5173)。Vite 固定使用 5173 端口，端口占用时会报错。`vite.config.ts` 将 `/api` 和 `/health` 代理至 `http://127.0.0.1:8000`；更换后端端口时需同步调整代理。

## 构建与预览

```powershell
npm run build
```

该命令先进行 TypeScript 项目构建检查，再输出 `dist/`。构建后在根目录重新启动 FastAPI，直接访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)，由同一个后端进程提供静态资源和 API。

`npm run preview` 仅预览静态构建；当前没有配置 preview API 代理，完整问答演示使用 FastAPI 提供的网页。

## 目录

| 文件 | 职责 |
| --- | --- |
| `src/App.tsx` | 问答、文献库、引用、轨迹和上传交互 |
| `src/api.ts` | HTTP 请求及错误处理，使用同源 `/api` 路径 |
| `src/types.ts` | 请求结果、引用来源和服务状态类型 |
| `src/styles.css` | 布局和页面样式 |
| `src/main.tsx` | React 入口及公式样式加载 |
| `vite.config.ts` | 开发端口与 API 代理 |

## 页面行为

- Enter 发送，Shift + Enter 换行。每个问题独立提交，页面中的历史不会作为模型上下文传入。
- `Top K` 仅控制普通 RAG 返回片段数；Agent 的检索预算由后端流程控制。
- 引用面板展示 PDF 页码或外部文献链接；只对 `rerank_relevance` 展示相关度分数。
- 轨迹来自后端返回的 `steps`，不是 Token 流式输出。
- “服务运行中”表示 API 请求可达，不代表模型 Key、Milvus 和 MCP 工具调用均已验证。
- 上传等待后端入库完成后展示页数与 Chunk 数。列表来自服务器 `data/papers/`，不是 Milvus 中所有历史记录。
- 页面状态不持久化，刷新或新建对话会清空当前对话展示。

MCP 在后端配置，详见 [MCP 接入](../docs/MCP.md)。接口字段及排错见 [Web 与 API 指南](../docs/WEB_QUICKSTART.md)。
