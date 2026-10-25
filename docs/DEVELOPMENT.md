# 开发、调试与 GitHub 发布

## 开发环境与检查

在项目根目录、Python 3.12 虚拟环境内执行：

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

开发依赖包含核心、API、MCP 和 TestClient 所需的 `httpx`。测试使用 Mock 和临时文件，覆盖分块、上下文、Registry、Graph 路由、API 契约、CLI 的 MCP 参数转发、API 的 MCP 生命周期和 MCP 响应字段兼容；不会调用模型、访问 Milvus 或启动真实 MCP Server。

`.github/workflows/ci.yml` 在 GitHub Push / Pull Request 时分别运行后端测试和前端构建，不要求配置模型密钥或启动数据库。

前端验证：

```powershell
cd frontend
npm ci
npm run build
cd ..
```

`npm run build` 包含 TypeScript 检查。修改依赖时同时提交 `package.json` 和 `package-lock.json`；日常复现环境使用 `npm ci`。

## CLI 调试参数

先检查实际参数：

```powershell
python -m main --help
python -m main rag --help
python -m main agent --help
```

| 用途 | 命令 |
| --- | --- |
| 普通 RAG | `python -m main rag --top-k 5` |
| 本地 Agent 与轨迹 | `python -m main agent --show-steps` |
| Agent + arXiv MCP | `python -m main agent --mcp-config configs/mcp_arxiv.json --show-steps` |

问题在程序启动后交互输入，不是位置参数。`rag` 的 `--top-k` 范围是 1–20，默认 5；`agent` 没有 `--top-k`，也没有旧版 `--retriever`。

IDE 的 Python 运行/调试配置：

- 解释器：本项目 `.venv/Scripts/python.exe`；macOS / Linux 为 `.venv/bin/python`。
- 模块名：`main`，或脚本路径：根目录 `main.py`，二选一。
- 程序参数：`agent --mcp-config configs/mcp_arxiv.json --show-steps`。
- 工作目录：项目根目录，确保 `.env` 和相对配置路径正确。
- 使用支持标准输入的终端，运行后输入问题。

`-m` 后面是模块名，因此使用 `python -m main`，不能写 `python -m main.py`；独立的 `--` 会终止选项解析，不应放在 `agent` 与其选项之间。

使用内置 pdb 也可调试：

```powershell
python -m pdb -m main agent --mcp-config configs/mcp_arxiv.json --show-steps
```

可按问题定位断点：`main.run_agent` 检查配置加载；`register_stdio_mcp` 检查工具发现；`actor_node` / `react_collect` 检查工具执行；`grader_node` 检查证据选择。

## Web 后端调试

IDE 中运行模块 `uvicorn`，参数：

```text
src.api.app:app --host 127.0.0.1 --port 8000
```

工作目录同样设为项目根目录，在该运行配置的环境变量或根目录 `.env` 中设置 `MCP_CONFIG_PATH=configs/mcp_arxiv.json`。断点调试时可省略 `--reload`，避免自动重载子进程使断点定位复杂。

前端在另一个终端运行 `npm run dev`。通过 `/docs` 可直接调试上传和问答，不必先启动网页。MCP 工具发现发生在 API lifespan 启动阶段，修改 JSON / `.env` 后应重启进程。

## 真实检索评测

```powershell
python -m evals.evaluate_retrieval
python -m evals.evaluate_retrieval --with-rerank
```

默认比较 Dense、Hybrid、Hybrid+EN，额外选项加入 Rerank；指标为 Hit@1、Hit@3、MRR@3、Recall@3。默认评测仍会调用 Embedding，中文查询还会调用 Chat 翻译；这不是离线单元测试。

`evals/retrieval_cases.json` 使用特定论文的人工标注。需要自行准备对应论文并使用匹配的文件名、页码和 800/100 分块规则导入。网页上传会更改保存文件名，因此不能直接复用原 Chunk ID。换用新资料时更新标注，不将空知识库或不匹配的标注结果视为项目效果。

## GitHub 提交准备

应提交源码、文档、依赖声明、前端锁文件、配置示例与 `.gitkeep`。`.gitignore` 已排除 `.env`、虚拟环境、IDE 配置、私有 PDF、日志、前端依赖、构建产物、TypeScript 缓存和 `configs/*.local.json`。

发布前确认：

1. 使用自己的有效配置完成一次入库、RAG、Agent，以及需要发布的 MCP 联调；单元测试不能代替真实服务验证。
2. 运行后端测试和前端构建，确认没有将真实密钥、本机绝对路径或私有论文加入待提交内容。
3. 将个人 MCP 可执行文件路径放入 `.local.json`，公开配置保留通用命令。
4. 根据项目归属决定是否公开及采用何种许可证；当前仓库未设置 `LICENSE`，文档不替维护者选择许可证。

若目录尚未初始化 Git，可执行以下本机准备命令；已有仓库直接检查待提交内容：

```powershell
git init
git branch -M main
git status --short --ignored
git check-ignore .env .venv/ frontend/node_modules/ frontend/dist/ logs/mcp_stderr.log
git add .
git diff --cached --stat
git diff --cached --name-only
```

核对暂存文件后再提交、配置自己的 GitHub 远端并推送。`.gitignore` 只影响未跟踪文件，不会移除已跟踪的敏感文件，也不会过滤手动打包上传的 ZIP；发布时按待提交清单检查。

服务停止使用 `docker compose stop` 即可保留数据。不要为了清理源码目录删除 Docker 数据卷；向量库不随 Git 仓库发布。
