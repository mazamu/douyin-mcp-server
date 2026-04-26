import os
import json
from openai import OpenAI


def split_copywriting_batch(copies: dict, api_key: str = None) -> dict:
    """
    对任意数量的文案进行拆分
    copies: {"文案A": "内容...", "文案B": "内容...", ...}
    api_key: DeepSeek API 密钥，不传则从环境变量 DEEPSEEK_API_KEY 读取
    返回: {"文案A": {"开头": {"原文": "...", "结构分析": "..."}, "核心观点": [...], "结尾": {...}}, ...}
    """
    api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("请设置环境变量 DEEPSEEK_API_KEY 或传入 api_key 参数")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )

    user_content = "请对以下文案逐条进行拆分（开头、核心观点、结尾），原封不动提取原文，核心观点数量不限：\n\n"
    for key, text in copies.items():
        user_content += f"【{key}】\n{text}\n\n"

    system_prompt = """
你是熟练使用文本解析工具的资深自媒体分析师。用户提供一个或多个文案（每个有唯一标识）。

任务：对每个文案独立拆分为开头、核心观点、结尾，对每一部分进行结构分析(包括如何引入的、有没有金句、是否针对痛点分析、核心利益点是什么...等等)。

要求：
1. 原文部分：原封不动，直接截取或提取原文句子，不总结、不删减、不改写。
2. 核心观点：按原文顺序列出所有主要论据/论点，数量不限（有几条就输出几条）。
3. 如果没有明确的开头/结尾划分，则第一段为开头，最后一段为结尾，中间为核心观点。
4. 输出纯JSON，JSON结构必须与输入文案的标识一致。

示例：
{
  "文案A": {
    "开头": {
      "原文": "...",
      "结构分析": "..."
    },
    "核心观点": [
      {
        "原文": "...",
        "结构分析": "..."
      },
      {
        "原文": "...",
        "结构分析": "..."
      }
    ],
    "结尾": {
      "原文": "...",
      "结构分析": "..."
    }
  },
  "文案B": { ... }
}
"""
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=1.6,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)


if __name__ == "__main__":
    test_copies = {
        "脚本1": "如果你不想上班，千万不要着急辞职...",
    }
    result = split_copywriting_batch(test_copies)
    print(json.dumps(result, ensure_ascii=False, indent=2))
