"""统一的 Qwen JSON 调用入口：复用项目 .env，不改变原有基础 RAG。"""
from __future__ import annotations

import asyncio
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _ask_json_sync(system_prompt: str, user_prompt: str) -> dict:
    with OpenAI(
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=os.environ["DASHSCOPE_BASE_URL"],
        timeout=60,
        max_retries=1,
    ) as client:
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-plus"),
            temperature=0,
            response_format={"type": "json_object"},  #大模型输出格式为json
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    value = json.loads(response.choices[0].message.content or "{}")  #将json解析为字典
    if not isinstance(value, dict):
        raise ValueError("LLM 未返回 JSON 对象")
    return value


async def ask_json(system_prompt: str, user_prompt: str) -> dict:
    """目前 SDK 为同步版，在线程中运行，避免阻塞 LangGraph 异步执行。"""
    return await asyncio.to_thread(_ask_json_sync, system_prompt, user_prompt)
