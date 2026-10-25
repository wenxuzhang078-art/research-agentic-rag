
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def translate_query(question: str) -> str:
    question = question.strip()

    if not question:
        raise ValueError("查询不能为空")

    # 没有中文字符时，直接使用原始问题
    if not any("\u4e00" <= c <= "\u9fff" for c in question):
        return question

    with OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url=os.getenv("DASHSCOPE_BASE_URL")
    ) as client:
        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "qwen-plus"),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一名科研检索查询翻译助手。"
                        "将用户关于多视图聚类的中文问题翻译成英文。"
                        "严格保持原始语义，不要回答问题，"
                        "不要补充用户未提到的算法、机制或结论。"
                        "只输出英文查询文本。"
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        )

    english_query = (
        response.choices[0].message.content or ""
    ).strip()

    if not english_query:
        raise RuntimeError("查询翻译结果为空")

    return english_query
