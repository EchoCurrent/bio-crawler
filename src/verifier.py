#!/usr/bin/env python3
"""
交叉验证模块
用AI验证信息的真实性和来源可靠性
"""

import asyncio
from typing import Dict, List, Optional
from loguru import logger

from .summarizer import KimiSummarizer
from .bfs_researcher import ResearchItem


class CrossVerifier:
    """交叉验证器"""

    VERIFICATION_PROMPT = """请验证以下科研信息的可信度，并找出相关来源：

标题: {title}
来源: {source}
分类: {category}
摘要: {summary}

请执行以下任务：
1. 判断该信息是否来自可信的科研来源（学术期刊、知名机构、权威媒体）
2. 搜索并列出2-3个独立的验证来源（不同机构/媒体）
3. 给出可信度评分（1-10）

输出JSON格式:
{{
    "is_credible": true/false,
    "credibility_score": 7,
    "verification_sources": ["来源1名称 - URL", "来源2名称 - URL", "来源3名称 - URL"],
    "reasoning": "判断理由...",
    "suggested_category": "准确的领域分类"
}}"""

    def __init__(self, summarizer: KimiSummarizer):
        self.summarizer = summarizer
        self.cache = {}  # 简单缓存避免重复验证

    async def verify_item(self, item: ResearchItem) -> ResearchItem:
        """验证单个条目"""
        if not self.summarizer.api_key or self.summarizer.api_key == "your-kimi-api-key-here":
            logger.warning("未配置Kimi API，跳过验证")
            return item

        # 检查缓存
        cache_key = f"{item.title}_{item.source}"
        if cache_key in self.cache:
            logger.debug(f"使用缓存验证结果: {item.title[:30]}")
            cached = self.cache[cache_key]
            item.verified = cached.get('is_credible', False)
            item.credibility_score = cached.get('credibility_score', 0)
            item.verification_sources = cached.get('verification_sources', [])
            return item

        try:
            prompt = self.VERIFICATION_PROMPT.format(
                title=item.title,
                source=item.source,
                category=item.category,
                summary=item.summary[:500] if item.summary else "无摘要"
            )

            # 调用Kimi API
            import httpx

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.summarizer.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.summarizer.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.summarizer.model,
                        "messages": [
                            {"role": "system", "content": "你是一个科研信息验证专家，擅长评估来源可信度和交叉验证。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1500
                    }
                )

                response.raise_for_status()
                result = response.json()

                content = result['choices'][0]['message']['content']
                parsed = self.summarizer._parse_json(content)

                if parsed:
                    # 缓存结果
                    self.cache[cache_key] = parsed

                    item.verified = parsed.get('is_credible', False)
                    item.credibility_score = parsed.get('credibility_score', 0)
                    item.verification_sources = parsed.get('verification_sources', [])

                    # 更新分类建议
                    suggested = parsed.get('suggested_category')
                    if suggested and suggested != item.category:
                        logger.debug(f"分类调整: {item.category} -> {suggested}")
                        item.category = suggested

                    logger.info(
                        f"验证完成: {item.title[:30]}... "
                        f"可信度={item.credibility_score}/10 "
                        f"{'✓' if item.verified else '✗'}"
                    )
                else:
                    logger.warning(f"验证结果解析失败: {item.title[:30]}")

        except Exception as e:
            logger.error(f"验证失败 {item.title[:30]}: {e}")

        return item

    async def verify_batch(self, items: List[ResearchItem], max_concurrent: int = 3) -> List[ResearchItem]:
        """批量验证（带并发控制）"""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def verify_with_semaphore(item):
            async with semaphore:
                return await self.verify_item(item)

        tasks = [verify_with_semaphore(item) for item in items]
        return await asyncio.gather(*tasks)

    def get_verification_stats(self, items: List[ResearchItem]) -> Dict:
        """获取验证统计"""
        total = len(items)
        verified = sum(1 for i in items if i.verified)
        high_credibility = sum(1 for i in items if i.credibility_score >= 7)

        return {
            "total": total,
            "verified": verified,
            "verification_rate": verified / total if total > 0 else 0,
            "high_credibility": high_credibility,
            "high_credibility_rate": high_credibility / total if total > 0 else 0,
        }
