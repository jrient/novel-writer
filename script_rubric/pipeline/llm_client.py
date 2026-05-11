from __future__ import annotations

import asyncio
import json
import re

import json_repair
from openai import AsyncOpenAI

from script_rubric.config import API_BASE_URL, API_KEY, MODEL, PASS1_CONCURRENCY

_semaphore = asyncio.Semaphore(PASS1_CONCURRENCY)


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=API_BASE_URL, api_key=API_KEY)


async def call_llm(
    client: AsyncOpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str = MODEL,
    max_retries: int = 2,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    async with _semaphore:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
        raise last_error


def extract_json(text: str) -> dict | list:
    text = text.strip()
    # 1. 尝试从 markdown code block 中提取
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = json_repair.loads(candidate)
            if isinstance(repaired, (dict, list)):
                return repaired
    # 2. 直接解析全文
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 3. 查找最外层 JSON 结构（dict 或 list）并修复
    #    优先使用最早出现的开括号来确定顶层类型
    candidates = []
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidates.append((start, open_ch, close_ch, text[start:end + 1]))
    # 按开括号位置排序，优先尝试最外层
    candidates.sort(key=lambda c: c[0])
    for _start, open_ch, close_ch, candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = json_repair.loads(candidate)
            if isinstance(repaired, (dict, list)):
                return repaired
    raise json.JSONDecodeError("No JSON object found in response", text, 0)
