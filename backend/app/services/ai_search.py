"""
AI增强搜索服务
使用Jina Reader API + OpenAI生成高质量知识摘要
"""
import os
import asyncio
import httpx
import logging
from typing import List, Dict, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def _get_proxy() -> Optional[str]:
    """从环境变量获取代理配置"""
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None


class AISearchService:
    def __init__(self, openai_api_key: str, openai_base_url: str, jina_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None):
        proxy = _get_proxy()
        http_client = httpx.AsyncClient(proxy=proxy) if proxy else None
        self.client = AsyncOpenAI(api_key=openai_api_key, base_url=openai_base_url, http_client=http_client)
        self.jina_api_key = jina_api_key
        self.gemini_api_key = gemini_api_key

    async def search(self, keyword: str, max_results: int = 3) -> List[Dict]:
        """AI增强搜索：跳过Gemini（代理不支持），回退Jina，最后使用OpenAI直接生成"""
        # 1. Gemini暂时禁用（代理配置问题）
        # if self.gemini_api_key:
        #     results = await self._gemini_search(keyword, max_results)
        #     if results:
        #         return results

        # 2. 回退到Jina + OpenAI
        search_content = await self._jina_search(keyword, max_retries=1)
        if search_content:
            knowledge_entries = await self._generate_knowledge(keyword, search_content, max_results)
            if knowledge_entries:
                return knowledge_entries

        # 3. 最终回退：直接使用OpenAI生成知识
        return await self._generate_knowledge_direct(keyword, max_results)

    async def _gemini_search(self, keyword: str, max_results: int) -> List[Dict]:
        """使用Gemini Google Search"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.gemini_api_key)

            model = genai.GenerativeModel('gemini-2.0-flash-exp',
                tools='google_search_retrieval')

            prompt = f"""搜索关键词"{keyword}"，生成{max_results}条高质量知识摘要。

要求：
1. 每条包含：title、content（200-400字）、url
2. 内容准确详实
3. 优先中文
4. 返回JSON：[{{"title":"...","content":"...","url":"..."}}]"""

            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt),
                timeout=300.0
            )

            import json
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)[:max_results]
        except asyncio.TimeoutError:
            logger.warning(f"Gemini搜索超时（300秒）")
            return []
        except Exception as e:
            logger.error(f"Gemini搜索失败: {e}")
            return []

    async def _jina_search(self, keyword: str, max_retries: int = 3) -> str:
        """使用Jina Reader API搜索，支持重试"""
        proxy = _get_proxy()

        for attempt in range(max_retries):
            try:
                headers = {"User-Agent": "NovelWriter/1.0"}
                if self.jina_api_key:
                    headers["Authorization"] = f"Bearer {self.jina_api_key}"

                async with httpx.AsyncClient(timeout=8.0, proxy=proxy) as client:
                    resp = await client.get(
                        f"https://s.jina.ai/{keyword}",
                        headers=headers
                    )
                    if resp.status_code == 200 and len(resp.text) > 100:
                        return resp.text[:8000]  # 限制长度

                    logger.warning(f"Jina搜索返回空内容，尝试 {attempt + 1}/{max_retries}")
            except Exception as e:
                logger.warning(f"Jina搜索失败 (尝试 {attempt + 1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # 重试前等待1秒

        return ""

    async def _generate_knowledge(self, keyword: str, search_content: str, max_results: int) -> List[Dict]:
        """用AI生成知识摘要"""
        prompt = f"""基于以下搜索内容，为关键词"{keyword}"生成{max_results}条高质量的知识摘要。

搜索内容：
{search_content}

要求：
1. 每条摘要包含：title（标题）、content（200-400字内容）、url（来源链接）
2. 内容要准确、详实、有价值
3. 优先使用中文
4. 返回JSON格式：[{{"title": "...", "content": "...", "url": "..."}}]

直接返回JSON数组，不要其他文字。"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            import json
            result_text = response.choices[0].message.content.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            knowledge_list = json.loads(result_text)
            return knowledge_list[:max_results]
        except Exception as e:
            logger.error(f"AI生成知识失败: {e}")
            return []

    async def _generate_knowledge_direct(self, keyword: str, max_results: int) -> List[Dict]:
        """直接使用OpenAI生成知识（无需搜索内容）"""
        prompt = f"""为关键词"{keyword}"生成{max_results}条高质量的知识摘要。

要求：
1. 每条摘要包含：title（标题）、content（200-400字详实内容）、url（设为"https://ai-generated"）
2. 内容要准确、详实、有价值
3. 优先使用中文
4. 返回JSON格式：[{{"title": "...", "content": "...", "url": "..."}}]

直接返回JSON数组，不要其他文字。"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            import json
            result_text = response.choices[0].message.content.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            knowledge_list = json.loads(result_text)
            return knowledge_list[:max_results]
        except Exception as e:
            logger.error(f"OpenAI直接生成知识失败: {e}")
            return []
