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
                    max_tokens=4096,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
        raise last_error


def extract_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = json_repair.loads(candidate)
            if isinstance(repaired, dict):
                return repaired
    raise json.JSONDecodeError("No JSON object found in response", text, 0)
