# MCP 接入与排错

本项目作为 MCP **Client**，按配置启动一个 stdio Server，发现白名单工具并注册到 Agent。默认只使用本地工具；普通 `rag` 模式不调用 MCP。当前配置是一份 Server 对象，不接受 `mcpServers` 包装、多 Server 列表或 HTTP MCP URL。

## 安装与示例配置

在项目根目录、已启用的虚拟环境中执行：

```powershell
python -m pip install -r requirements-mcp.txt
python -m pip install uv
uvx --version
```

`mcp` 是 Python Client 依赖，`uvx` 用于启动外部 Server，两者都需要。首次启动时 `uvx` 可能下载 Server 及依赖，需要网络；安装后端依赖本身不会预装该 Server。

仓库提供的 `configs/mcp_arxiv.json`：

```json
{
  "server_id": "arxiv",
  "command": "uvx",
  "args": ["--from", "arxiv-mcp-server==0.8.2", "arxiv-mcp-server"],
  "allowed_tools": ["search_papers", "get_abstract"]
}
```

该配置固定使用 [`arxiv-mcp-server` v0.8.2](https://github.com/blazickjp/arxiv-mcp-server/blob/v0.8.2/README.md)，只允许搜索和摘要工具。上游工具变化时，须同时核对版本、工具名、参数 Schema 和 `src/integrations/arxiv_adapter.py`。

| 字段 | 含义 |
| --- | --- |
| `server_id` | 注册名前缀；值为 `arxiv` 时启用本项目的 arXiv 证据适配 |
| `command` | 可执行文件名或绝对路径，不是整条 shell 命令 |
| `args` | 独立参数数组，可省略，默认空列表 |
| `allowed_tools` | 必填工具白名单；仅注册 Server 实际发现且名称匹配的工具 |

Server 的工作目录固定为项目根目录。当前配置不提供自定义 `env` 字段；需要凭据的其他 Server 须自行扩展受控环境变量传递。不要在公开配置中保存密钥；个人配置可保存为被忽略的 `configs/arxiv.local.json`。

## CLI 启用

```powershell
python -m main agent --mcp-config configs/mcp_arxiv.json --show-steps
```

输入问题后会先执行 MCP Discovery，成功时终端显示注册的工具名，再运行 Agent。预期工具名：

```text
mcp_arxiv_search_papers
mcp_arxiv_get_abstract
```

`python main.py agent --mcp-config configs/mcp_arxiv.json --show-steps` 等价。`MCP_CONFIG_PATH` 用于 Web 后端，CLI 需显式传 `--mcp-config`；不要使用 `python -m main.py` 或在 `agent` 后插入独立的 `--`。

注册只影响当前 Python 进程。在另一个终端运行 CLI 并不会启用已经运行的 Web 后端。CLI 的 MCP 初始化失败会直接退出；不传该参数即可使用本地 Agent。

## Web 后端启用

PowerShell，在启动 API 的同一个终端设置：

```powershell
$env:MCP_CONFIG_PATH = "configs/mcp_arxiv.json"
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

也可在根目录 `.env` 中填写 `MCP_CONFIG_PATH=configs/mcp_arxiv.json` 后启动。macOS / Linux 可使用：

```bash
MCP_CONFIG_PATH=configs/mcp_arxiv.json python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

访问或请求 [API 状态](http://127.0.0.1:8000/api/status)：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

- `disabled`：未配置路径。
- `connected`：启动时工具发现/注册已完成；检查 `mcp_tools` 是否包含预期工具。空列表通常意味着白名单没有匹配到工具。
- `error`：初始化失败，查看 API 终端异常和 `logs/mcp_stderr.log`。API 仍会启动，本地 RAG / Agent 可继续尝试运行。

`connected` 不是持续连接或真实搜索成功的证明。目前 Discovery 和每次工具调用分别启动、关闭一次 stdio 子进程。工具是否实际执行，应查看问答返回的 `steps` → `act` → `calls`；工具调用失败也可能只记录在轨迹中。

更改配置后重启 API；`--reload` 不保证监听 `.env` 或 JSON 文件的变化。关闭 MCP 时，将 `.env` 中的值留空，并清除当前终端变量后重启：

```powershell
Remove-Item Env:MCP_CONFIG_PATH -ErrorAction SilentlyContinue
```

## 证据返回约定

arXiv 工具返回的标题、作者、摘要等元数据由专用 Adapter 转为带 `source_url` 的证据，不写入 Milvus，不自动下载全文。`search_papers` 最多适配 10 篇；外部证据标为 `unscored_external`，交给 Grade 语义审核，不套用本地 Rerank 门槛。

接入其他 Server 时，除非实现专用 Adapter，否则返回 JSON 对象应包含标准 `hits`：

```json
{
  "hits": [
    {
      "chunk_id": "paper-1-p2-c0",
      "content": "可引用的原文片段",
      "source": "paper.pdf",
      "page": 2
    }
  ]
}
```

通用适配要求非空字符串 `chunk_id`、`content`、`source` 和整数 `page`，最多接收 20 条；不符合约定的条目会被忽略。仅返回普通文本或其他业务 JSON 可以成为工具观察结果，但不会自动产生可引用证据。工具 `isError` 或业务 `status=error/rate_limited/unavailable` 会转成工具错误。

## 常见问题

| 现象 | 检查方式 |
| --- | --- |
| `No module named mcp` | 在运行后端的同一虚拟环境安装 `requirements-mcp.txt` |
| 找不到 `uvx` / `WinError 2` | 运行 `(Get-Command uvx).Source`，必要时将 `command` 改成该绝对路径；本机路径放入个人 `.local.json` |
| Server 启动失败或依赖下载慢 | 查看 `logs/mcp_stderr.log`；单独运行 `uvx --from arxiv-mcp-server==0.8.2 arxiv-mcp-server --help` 检查安装和入口 |
| 状态为 `connected`，但未使用 MCP | 切换 Agent 模式并提出需要外部文献的问题；是否调用由模型根据已有证据决定 |
| 工具返回条目但没有引用 | 检查 Adapter、标准 `hits` 字段，以及 Grade 的相关性判断 |
| arXiv 限流或不可用 | 查看工具错误并稍后重试；服务发现成功不代表上游检索可用 |
| 改了配置仍未生效 | 检查启动终端中的环境变量是否覆盖 `.env`，然后完全重启后端 |

配置会启动本机外部程序，仅使用审核过的命令与只读工具白名单。Registry 的 `read_only` 标记不是操作系统沙箱，远端行为由具体 Server 实现决定。
