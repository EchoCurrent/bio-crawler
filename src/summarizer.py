#!/usr/bin/env python3
"""
Kimi AI 摘要生成模块
"""

import json
import re
from typing import Dict, List, Optional

import httpx
from loguru import logger


class KimiSummarizer:
    """Kimi AI 摘要生成器"""

    PROMPT_TEMPLATE = """请对以下微信公众号文章进行分析，输出JSON格式结果：

标题: {title}
作者: {author}
公众号: {account_name}
发布时间: {publish_time}

正文:
{content}

请输出以下JSON结构（只输出JSON，不要其他内容）:
{{
    "summary_short": "一句话概括核心观点（50字内）",
    "summary_long": "详细摘要（200-300字）",
    "key_points": ["要点1", "要点2", "要点3"],
    "tags": ["标签1", "标签2", "标签3"],
    "sentiment": "positive|neutral|negative",
    "category": "科技|商业|社会|文化|娱乐|其他"
}}"""

    def __init__(
        self,
        api_key: str,
        model: str = "kimi-k3",
        api_base: str = "https://api.moonshot.cn/v1",
        max_content_length: int = 8000
    ):
        self.api_key = api_key
        self.model = model
        self.api_base = api_base.rstrip('/')
        self.max_content_length = max_content_length
        self.http = httpx.AsyncClient(timeout=60.0)

    async def summarize(self, article: Dict) -> Optional[Dict]:
        """生成文章摘要

        Args:
            article: 文章数据，需包含 title, content_text 等字段

        Returns:
            摘要结果字典，失败返回None
        """
        if not self.api_key or self.api_key == "your-kimi-api-key-here":
            logger.warning("Kimi API Key 未配置，跳过摘要生成")
            return None

        try:
            # 准备内容
            content = article.get('content_text', '')
            if not content:
                logger.warning("文章无正文，跳过摘要")
                return None

            # 截断过长的内容
            if len(content) > self.max_content_length:
                content = content[:self.max_content_length] + "..."

            # 构建prompt
            prompt = self.PROMPT_TEMPLATE.format(
                title=article.get('title', '无标题'),
                author=article.get('author', '未知'),
                account_name=article.get('account_name', '未知'),
                publish_time=article.get('publish_time', '未知'),
                content=content
            )

            # 调用Kimi API
            logger.debug(f"调用Kimi API，模型: {self.model}")

            response = await self.http.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "你是一个专业的文章分析助手，擅长提取文章要点和生成摘要。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                }
            )

            response.raise_for_status()
            result = response.json()

            # 解析结果
            content = result['choices'][0]['message']['content']
            parsed = self._parse_json(content)

            if parsed:
                parsed['model_used'] = self.model
                logger.info(f"摘要生成成功: {parsed.get('summary_short', '')[:50]}...")
                return parsed
            else:
                logger.warning("Kimi返回结果解析失败")
                return None

        except httpx.HTTPStatusError as e:
            logger.error(f"Kimi API 错误: {e.response.status_code} - {e.response.text[:200]}")
            return None
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            return None

    def _parse_json(self, text: str) -> Optional[Dict]:
        """从文本中提取JSON"""
        # 尝试匹配markdown code block
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'\{[^{}]*\}',  # 简单匹配花括号
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # 尝试直接解析整个文本
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        return None

    async def batch_summarize(
        self,
        articles: List[Dict],
        batch_size: int = 3
    ) -> List[Optional[Dict]]:
        """批量生成摘要"""
        results = []

        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            logger.info(f"批量摘要: {i+1}-{min(i+batch_size, len(articles))}/{len(articles)}")

            tasks = [self.summarize(article) for article in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理异常
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"摘要生成异常: {result}")
                    results.append(None)
                else:
                    results.append(result)

        return results
