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
        last_error: Exception | None = None
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
        assert last_error is not None
        raise last_error


def _try_load(candidate: str) -> dict | list | None:
    """逐级尝试解析：strict json -> json_repair。任何一步异常都吞掉返回 None。"""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        repaired = json_repair.loads(candidate)
        if isinstance(repaired, (dict, list)):
            return repaired
    except Exception:
        pass
    return None


def extract_json(text: str) -> dict | list:
    text = text.strip()
    # 1. markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        result = _try_load(match.group(1).strip())
        if result is not None:
            return result
    # 2. 直接解析全文
    result = _try_load(text)
    if result is not None:
        return result
    # 3. 在原文中按开括号位置定位最外层 JSON 结构
    candidates: list[tuple[int, str]] = []
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidates.append((start, text[start:end + 1]))
    candidates.sort(key=lambda c: c[0])
    for _start, candidate in candidates:
        result = _try_load(candidate)
        if result is not None:
            return result
    raise json.JSONDecodeError("No JSON object found in response", text, 0)
