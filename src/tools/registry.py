"""Agent 工具注册中心：统一注册、参数校验、执行和 Function Calling 描述。"""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from jsonschema import Draft202012Validator
from src.tools.local_search import rag_search, read_chunk



# 1. 定义工具契约
ToolFn = Callable[[dict[str, Any]],Awaitable[dict[str, Any]]]

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    execute: ToolFn
    provider: str = "local"
    read_only: bool = True


# 2. 注册表管理类
class ToolRegistry:

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
   #注册工具
    def register(self, spec: ToolSpec) -> None:
        if not spec.name or not spec.name.strip():
            raise ValueError("工具名称不能为空")
        if spec.name in self._tools:
            raise ValueError(f"工具名重复：{spec.name}")
        if not spec.read_only:
            raise ValueError("只允许注册只读工具")
        # 在注册时检查 JSON Schema 自身是否合法
        Draft202012Validator.check_schema(spec.parameters)
        self._tools[spec.name] = spec
    #根据名称调工具
    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name] #返回工具
        except KeyError as exc:
            raise ValueError(f"未注册工具：{name}") from exc

    def validate(self,name: str,arguments: dict[str, Any]) -> None:
        """检查工具调用参数是否符合对应 Schema。"""
        spec = self.get(name)
        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        Draft202012Validator(spec.parameters).validate(arguments)

    async def execute(self, name: str,arguments: dict[str, Any]) -> dict[str, Any]:
        # 第一步：参数校验
        self.validate(name, arguments)
        # 第二步：取得对应工具
        spec = self.get(name)
        # 第三步：执行工具
        result = await spec.execute(arguments)
        # 第四步：校验结果类型
        if not isinstance(result, dict):
            raise TypeError(f"{name} 必须返回字典")

        hits = result.get("hits", [])

        if not isinstance(hits, list):
            raise TypeError(f"{name}.hits 必须是列表")

        return {**result,"hits": hits,"provider": spec.provider}
    #"""获取工具目录，用于展示及 Planner。"""
    def catalog(self) -> list[dict[str, str]]:

        return [
            {
                "name": spec.name,
                "description": spec.description,
                "provider": spec.provider
            }
            for spec in self._tools.values()
        ]

    def definitions(self) -> list[dict[str, Any]]:
        """生成 Qwen 原生 Function Calling 工具描述。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters
                }
            }
            for spec in self._tools.values()
        ]



# 3. 本地工具适配函数
async def _rag(args: dict[str, Any]) -> dict[str, Any]:
    return await rag_search(args["query"],args.get("top_k", 8) )

async def _read(args: dict[str, Any]) -> dict[str, Any]:
    return await read_chunk(args["chunk_id"])



# 4. 本地工具参数 Schema

RAG_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
            "description": "用于本地论文库检索证据的独立问题"
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 8
        }
    },
    "required": ["query"],
    "additionalProperties": False
}


READ_SCHEMA = {
    "type": "object",
    "properties": {
        "chunk_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 128,
            "description": "已检索到的精确 chunk_id"
        }
    },
    "required": ["chunk_id"],
    "additionalProperties": False
}



# 5. 注册内置工具

def register_builtin_tools(registry: ToolRegistry) -> None:

    registry.register(
        ToolSpec(name="rag_search",
            description=(
                "本地论文完整 RAG 检索："
                "Embedding、Dense+BM25、RRF、Rerank，"
                "返回可引用证据。"
            ),
            parameters=RAG_SCHEMA,
            execute=_rag
        )
    )

    registry.register(
        ToolSpec(
            name="read_chunk",
            description=("按已知 chunk_id 续读论文原文及来源，"
                "不产生新的相关性分数。"
            ),
            parameters=READ_SCHEMA,
            execute=_read
        )
    )



# 6. 创建应用共享注册表
tool_registry = ToolRegistry()
# 启动时注册两个内置工具
register_builtin_tools(tool_registry)
