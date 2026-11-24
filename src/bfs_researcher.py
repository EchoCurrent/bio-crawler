#!/usr/bin/env python3
"""
广度优先搜索研究模块
基于公众号线索，进行网络深度搜索和交叉验证
"""

import asyncio
import re
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import quote_plus, urlparse
import httpx
from bs4 import BeautifulSoup
from loguru import logger


@dataclass
class ResearchItem:
    """研究条目"""
    title: str
    url: str
    source: str  # 来源：公众号/网站/搜索引擎
    source_type: str  # wechat/website/search_engine
    category: str  # 领域分类
    keywords: List[str] = field(default_factory=list)
    summary: str = ""
    verified: bool = False
    credibility_score: int = 0  # 可信度评分 1-10
    verification_sources: List[str] = field(default_factory=list)
    publish_time: str = ""
    extra: Dict = field(default_factory=dict)  # 额外数据

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "source_type": self.source_type,
            "category": self.category,
            "keywords": ", ".join(self.keywords[:5]) if self.keywords else "",
            "summary": self.summary,
            "verified": "是" if self.verified else "否",
            "credibility_score": self.credibility_score,
            "verification_count": len(self.verification_sources),
            "verification_sources": "; ".join(self.verification_sources[:3]),
            "publish_time": self.publish_time,
        }


class BFSResearcher:
    """广度优先搜索研究器"""

    def __init__(self, max_depth: int = 2, max_results_per_keyword: int = 10):
        self.max_depth = max_depth
        self.max_results = max_results_per_keyword
        self.visited_urls: Set[str] = set()
        self.session = None
        self._init_session()

    def _init_session(self):
        """初始化HTTP会话"""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }
        )

    async def close(self):
        """关闭会话"""
        if self.session:
            await self.session.aclose()

    async def research(
        self,
        seed_items: List[ResearchItem],
        categories: Dict[str, Dict]
    ) -> List[ResearchItem]:
        """基于种子条目进行广度优先搜索

        Args:
            seed_items: 种子条目（来自公众号/网站）
            categories: 领域分类配置

        Returns:
            扩展后的研究条目列表
        """
        all_items = list(seed_items)
        current_level = list(seed_items)

        # 将种子URL加入已访问
        for item in seed_items:
            self.visited_urls.add(item.url)

        for depth in range(self.max_depth):
            logger.info(f"BFS深度 {depth + 1}/{self.max_depth}")
            next_level = []

            for item in current_level:
                # 基于当前条目搜索相关内容
                new_items = await self._expand_item(item, categories)

                # 去重并添加到结果
                for new_item in new_items:
                    if new_item.url not in self.visited_urls and new_item.url:
                        self.visited_urls.add(new_item.url)
                        next_level.append(new_item)
                        all_items.append(new_item)

                # 控制并发
                await asyncio.sleep(0.5)

            current_level = next_level[:20]  # 限制每层扩展数量
            logger.info(f"深度 {depth + 1}: 发现 {len(next_level)} 个新条目")

        return all_items

    async def _expand_item(
        self,
        item: ResearchItem,
        categories: Dict[str, Dict]
    ) -> List[ResearchItem]:
        """扩展单个条目"""
        new_items = []

        # 提取关键词
        keywords = item.keywords or self._extract_keywords(item.title)

        # 用关键词搜索（限制数量避免请求过多）
        for keyword in keywords[:2]:
            # 必应搜索
            bing_results = await self._search_bing(keyword, item.category)
            new_items.extend(bing_results)

            # 百度搜索
            baidu_results = await self._search_baidu(keyword, item.category)
            new_items.extend(baidu_results)

        return new_items[:10]  # 限制每个条目扩展数量

    def _extract_keywords(self, title: str) -> List[str]:
        """从标题提取关键词"""
        # 简单实现：提取英文单词和中文词组
        words = []

        # 提取英文单词（长度>=4）
        english_words = re.findall(r'[a-zA-Z]{4,}', title)
        words.extend(english_words[:3])

        # 提取中文词组（简单按空格和标点分割）
        chinese_parts = re.split(r'[\s,，。;；:：!！?？\-_/\\]', title)
        for part in chinese_parts:
            if 2 <= len(part) <= 10 and re.search(r'[一-鿿]', part):
                words.append(part)

        return words[:5] if words else [title[:10]]

    async def _search_bing(self, keyword: str, category: str) -> List[ResearchItem]:
        """必应搜索"""
        try:
            url = f"https://www.bing.com/search?q={quote_plus(keyword)}&count=10"
            logger.debug(f"必应搜索: {keyword}")

            response = await self.session.get(url)
            soup = BeautifulSoup(response.text, 'lxml')

            items = []
            for result in soup.select('li.b_algo')[:5]:
                title_el = result.select_one('h2 a')
                if not title_el:
                    continue

                href = title_el.get('href', '')
                if not href or href in self.visited_urls:
                    continue

                # 提取摘要
                snippet_el = result.select_one('.b_caption p')
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                items.append(ResearchItem(
                    title=title_el.get_text(strip=True),
                    url=href,
                    source="Bing",
                    source_type="search_engine",
                    category=category,
                    keywords=[keyword],
                    summary=snippet[:200],
                    publish_time=""
                ))

            logger.debug(f"必应搜索 '{keyword}': {len(items)} 条结果")
            return items

        except Exception as e:
            logger.error(f"必应搜索失败: {e}")
            return []

    async def _search_baidu(self, keyword: str, category: str) -> List[ResearchItem]:
        """百度搜索"""
        try:
            url = f"https://www.baidu.com/s?wd={quote_plus(keyword)}&rn=10"
            logger.debug(f"百度搜索: {keyword}")

            response = await self.session.get(url)
            soup = BeautifulSoup(response.text, 'lxml')

            items = []
            for result in soup.select('div.result, div.c-container')[:5]:
                title_el = result.select_one('h3 a')
                if not title_el:
                    continue

                href = title_el.get('href', '')
                if not href or href in self.visited_urls:
                    continue

                # 提取摘要
                snippet_el = result.select_one('.c-abstract, .content-right_8Zs40, [class*="content"]')
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                items.append(ResearchItem(
                    title=title_el.get_text(strip=True),
                    url=href,
                    source="百度",
                    source_type="search_engine",
                    category=category,
                    keywords=[keyword],
                    summary=snippet[:200],
                    publish_time=""
                ))

            logger.debug(f"百度搜索 '{keyword}': {len(items)} 条结果")
            return items

        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return []

    async def search_direct(
        self,
        keywords: List[str],
        category: str = "通用"
    ) -> List[ResearchItem]:
        """直接搜索关键词（不基于种子条目）"""
        all_items = []

        for keyword in keywords:
            # 必应搜索
            bing_results = await self._search_bing(keyword, category)
            all_items.extend(bing_results)

            # 百度搜索
            baidu_results = await self._search_baidu(keyword, category)
            all_items.extend(baidu_results)

            await asyncio.sleep(1)  # 控制请求频率

        return all_items
