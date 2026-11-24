#!/usr/bin/env python3
"""
AI驱动的智能研究系统 v3.0
核心特点：
1. Claude自主规划搜索策略
2. 智能评估和过滤搜索结果
3. 动态调整研究方向
4. 自动生成交叉验证报告

使用方法:
    export ANTHROPIC_API_KEY=your-api-key
    python demo_ai_research.py --demo basic
"""

import asyncio
import json
import re
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

import anthropic
import httpx
from bs4 import BeautifulSoup
from loguru import logger


class CredibilityLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelevanceLevel(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ResearchFinding:
    """研究发现"""
    id: str
    topic: str
    content: str
    source: str
    url: str
    credibility: CredibilityLevel
    relevance: RelevanceLevel
    key_points: List[str] = field(default_factory=list)
    evidence_strength: str = "moderate"  # strong/moderate/weak
    contradictions: List[str] = field(default_factory=list)
    supporting_sources: List[str] = field(default_factory=list)
    publish_date: Optional[str] = None
    extracted_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "content": self.content[:500] + "..." if len(self.content) > 500 else self.content,
            "source": self.source,
            "url": self.url,
            "credibility": self.credibility.value,
            "relevance": self.relevance.value,
            "key_points": self.key_points[:5],
            "evidence_strength": self.evidence_strength,
            "publish_date": self.publish_date,
            "extracted_at": self.extracted_at.isoformat()
        }


@dataclass
class SearchResult:
    """搜索结果"""
    title: str
    url: str
    snippet: str
    source: str
    search_engine: str
    query_used: str


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict] = {}

    def register(self, name: str, schema: Dict, func: Callable):
        """注册工具"""
        self.tools[name] = func
        self.schemas[name] = schema

    async def execute(self, name: str, params: Dict) -> Any:
        """执行工具"""
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found"}

        try:
            result = await self.tools[name](**params)
            return result
        except Exception as e:
            logger.error(f"Tool '{name}' execution failed: {e}")
            return {"error": str(e)}

    def get_schemas(self) -> List[Dict]:
        """获取所有工具schema"""
        return [
            {
                "name": name,
                "description": schema.get("description", ""),
                "input_schema": schema.get("input_schema", {})
            }
            for name, schema in self.schemas.items()
        ]


class SearchEngine:
    """搜索引擎集成"""

    def __init__(self):
        self.http = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        )

    async def search_bing(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """必应搜索"""
        try:
            url = f"https://www.bing.com/search?q={query}&count={max_results}"
            response = await self.http.get(url)
            soup = BeautifulSoup(response.text, 'lxml')

            results = []
            for item in soup.select('li.b_algo')[:max_results]:
                title_el = item.select_one('h2 a')
                if not title_el:
                    continue

                snippet_el = item.select_one('.b_caption p')
                results.append(SearchResult(
                    title=title_el.get_text(strip=True),
                    url=title_el.get('href', ''),
                    snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                    source="Bing",
                    search_engine="bing",
                    query_used=query
                ))

            return results

        except Exception as e:
            logger.error(f"Bing search failed: {e}")
            return []

    async def search_baidu(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """百度搜索"""
        try:
            from urllib.parse import quote_plus
            url = f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={max_results}"
            response = await self.http.get(url)
            soup = BeautifulSoup(response.text, 'lxml')

            results = []
            for item in soup.select('div.result, div.c-container')[:max_results]:
                title_el = item.select_one('h3 a')
                if not title_el:
                    continue

                snippet_el = item.select_one('.c-abstract, [class*="content"]')
                results.append(SearchResult(
                    title=title_el.get_text(strip=True),
                    url=title_el.get('href', ''),
                    snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                    source="百度",
                    search_engine="baidu",
                    query_used=query
                ))

            return results

        except Exception as e:
            logger.error(f"Baidu search failed: {e}")
            return []

    async def search_academic(
        self,
        query: str,
        sources: List[str] = None
    ) -> List[SearchResult]:
        """学术搜索（PubMed, bioRxiv等）"""
        # 这里可以集成PubMed E-utilities API
        # 目前返回空列表，需要API key
        return []

    async def fetch_content(self, url: str) -> Dict:
        """抓取网页内容"""
        try:
            response = await self.http.get(url)
            soup = BeautifulSoup(response.text, 'lxml')

            # 提取标题
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else ""

            # 提取正文
            article = soup.find('article') or soup.find('main') or soup.find('body')
            content = article.get_text(separator='\n', strip=True) if article else ""

            # 提取元数据
            meta = {}
            for meta_tag in soup.find_all('meta'):
                name = meta_tag.get('name') or meta_tag.get('property')
                if name:
                    meta[name] = meta_tag.get('content', '')

            return {
                "url": url,
                "title": title_text,
                "content": content[:10000],  # 限制长度
                "metadata": meta,
                "success": True
            }

        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return {
                "url": url,
                "error": str(e),
                "success": False
            }

    async def close(self):
        """关闭HTTP客户端"""
        await self.http.aclose()


class AIResearchSystem:
    """AI驱动的研究系统"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-5-5",
        enable_search: bool = True
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.enable_search = enable_search

        # 初始化组件
        self.search_engine = SearchEngine()
        self.tool_registry = ToolRegistry()
        self.findings: List[ResearchFinding] = []
        self.conversation_history = []

        # 注册工具
        self._register_tools()

        # 研究状态
        self.current_topic = ""
        self.research_questions = []
        self.search_iteration = 0
        self.max_iterations = 15

    def _register_tools(self):
        """注册可用工具"""

        # 搜索工具
        self.tool_registry.register(
            name="web_search",
            schema={
                "description": "搜索网页信息，支持多个搜索引擎",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，支持中英文"
                        },
                        "search_engine": {
                            "type": "string",
                            "enum": ["bing", "baidu", "academic", "all"],
                            "description": "搜索引擎选择"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最大结果数",
                            "default": 10
                        },
                        "time_range": {
                            "type": "string",
                            "enum": ["day", "week", "month", "year", "all"],
                            "description": "时间范围过滤"
                        }
                    },
                    "required": ["query"]
                }
            },
            func=self._tool_web_search
        )

        # 网页抓取工具
        self.tool_registry.register(
            name="fetch_webpage",
            schema={
                "description": "获取网页详细内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "网页URL"
                        },
                        "extract_images": {
                            "type": "boolean",
                            "description": "是否提取图片",
                            "default": False
                        }
                    },
                    "required": ["url"]
                }
            },
            func=self._tool_fetch_webpage
        )

        # 保存发现工具
        self.tool_registry.register(
            name="save_finding",
            schema={
                "description": "保存研究发现，包括可信度评估",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "研究主题"},
                        "content": {"type": "string", "description": "主要内容"},
                        "source": {"type": "string", "description": "来源名称"},
                        "url": {"type": "string", "description": "来源URL"},
                        "credibility": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "可信度评估"
                        },
                        "relevance": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "相关度评估"
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键观点列表"
                        },
                        "evidence_strength": {
                            "type": "string",
                            "enum": ["strong", "moderate", "weak"],
                            "description": "证据强度"
                        }
                    },
                    "required": ["topic", "content", "source", "url", "credibility", "relevance"]
                }
            },
            func=self._tool_save_finding
        )

        # 交叉验证工具
        self.tool_registry.register(
            name="cross_verify",
            schema={
                "description": "交叉验证信息的准确性",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "finding_id": {
                            "type": "string",
                            "description": "要验证的发现ID"
                        },
                        "verification_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "验证来源URL列表"
                        }
                    },
                    "required": ["finding_id"]
                }
            },
            func=self._tool_cross_verify
        )

        # 生成报告工具
        self.tool_registry.register(
            name="generate_report",
            schema={
                "description": "生成最终研究报告",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "报告标题"},
                        "summary": {"type": "string", "description": "执行摘要"},
                        "key_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键发现列表"
                        },
                        "methodology": {
                            "type": "string",
                            "description": "研究方法说明"
                        },
                        "limitations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "研究局限性"
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "建议"
                        }
                    },
                    "required": ["title", "summary"]
                }
            },
            func=self._tool_generate_report
        )

        # 调整研究方向工具
        self.tool_registry.register(
            name="adjust_direction",
            schema={
                "description": "根据当前发现调整研究方向",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "调整原因"
                        },
                        "new_questions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "新的研究问题"
                        },
                        "priority_shift": {
                            "type": "string",
                            "description": "优先级调整说明"
                        }
                    },
                    "required": ["reason", "new_questions"]
                }
            },
            func=self._tool_adjust_direction
        )

    # ==================== 工具实现 ====================

    async def _tool_web_search(
        self,
        query: str,
        search_engine: str = "all",
        max_results: int = 10,
        time_range: str = "all"
    ) -> Dict:
        """网页搜索工具"""
        logger.info(f"[Tool] web_search: {query} (engine={search_engine})")

        if not self.enable_search:
            return {"error": "Search is disabled", "results": []}

        all_results = []

        # 根据选择执行搜索
        if search_engine in ["bing", "all"]:
            bing_results = await self.search_engine.search_bing(query, max_results)
            all_results.extend(bing_results)

        if search_engine in ["baidu", "all"]:
            baidu_results = await self.search_engine.search_baidu(query, max_results)
            all_results.extend(baidu_results)

        if search_engine == "academic":
            academic_results = await self.search_engine.search_academic(query)
            all_results.extend(academic_results)

        # 转换为字典格式
        results_dict = [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet[:300],
                "source": r.source,
                "search_engine": r.search_engine
            }
            for r in all_results[:max_results]
        ]

        return {
            "query": query,
            "total_results": len(results_dict),
            "results": results_dict
        }

    async def _tool_fetch_webpage(self, url: str, extract_images: bool = False) -> Dict:
        """网页抓取工具"""
        logger.info(f"[Tool] fetch_webpage: {url}")
        return await self.search_engine.fetch_content(url)

    async def _tool_save_finding(self, **kwargs) -> Dict:
        """保存研究发现"""
        finding_id = f"finding_{len(self.findings) + 1:03d}"

        finding = ResearchFinding(
            id=finding_id,
            topic=kwargs.get("topic", ""),
            content=kwargs.get("content", ""),
            source=kwargs.get("source", ""),
            url=kwargs.get("url", ""),
            credibility=CredibilityLevel(kwargs.get("credibility", "medium")),
            relevance=RelevanceLevel(kwargs.get("relevance", "medium")),
            key_points=kwargs.get("key_points", []),
            evidence_strength=kwargs.get("evidence_strength", "moderate"),
            publish_date=kwargs.get("publish_date")
        )

        self.findings.append(finding)
        logger.info(f"[Tool] Saved finding: {finding_id} - {finding.topic[:50]}")

        return {
            "status": "saved",
            "finding_id": finding_id,
            "total_findings": len(self.findings)
        }

    async def _tool_cross_verify(
        self,
        finding_id: str,
        verification_sources: List[str] = None
    ) -> Dict:
        """交叉验证工具"""
        # 查找对应发现
        finding = next((f for f in self.findings if f.id == finding_id), None)
        if not finding:
            return {"error": f"Finding {finding_id} not found"}

        logger.info(f"[Tool] cross_verify: {finding_id}")

        # 这里可以实现自动验证逻辑
        # 目前返回需要手动验证的提示

        return {
            "finding_id": finding_id,
            "verification_needed": True,
            "suggested_sources": verification_sources or [],
            "message": "Please manually verify this finding with the suggested sources"
        }

    async def _tool_generate_report(self, **kwargs) -> Dict:
        """生成报告工具"""
        logger.info("[Tool] generate_report")

        report = {
            "title": kwargs.get("title", "Research Report"),
            "summary": kwargs.get("summary", ""),
            "key_findings": kwargs.get("key_findings", []),
            "methodology": kwargs.get("methodology", ""),
            "limitations": kwargs.get("limitations", []),
            "recommendations": kwargs.get("recommendations", []),
            "total_findings": len(self.findings),
            "high_credibility_findings": len([f for f in self.findings if f.credibility == CredibilityLevel.HIGH]),
            "high_relevance_findings": len([f for f in self.findings if f.relevance == RelevanceLevel.HIGH]),
            "generated_at": datetime.now().isoformat()
        }

        return report

    async def _tool_adjust_direction(
        self,
        reason: str,
        new_questions: List[str],
        priority_shift: str = ""
    ) -> Dict:
        """调整研究方向"""
        logger.info(f"[Tool] adjust_direction: {reason}")

        self.research_questions = new_questions

        return {
            "status": "direction_adjusted",
            "new_questions": new_questions,
            "message": f"Research direction adjusted: {reason}"
        }

    # ==================== 核心研究流程 ====================

    async def research(
        self,
        topic: str,
        research_questions: Optional[List[str]] = None,
        context: Optional[str] = None,
        max_iterations: int = 15
    ) -> Dict:
        """
        执行AI驱动的研究

        Args:
            topic: 研究主题
            research_questions: 具体研究问题
            context: 额外上下文
            max_iterations: 最大迭代次数

        Returns:
            完整的研究结果
        """
        self.current_topic = topic
        self.research_questions = research_questions or []
        self.max_iterations = max_iterations

        logger.info("=" * 70)
        logger.info(f"Starting AI-driven research: {topic}")
        logger.info("=" * 70)

        # 构建初始消息
        initial_content = f"""请帮我深入研究以下主题：

**主题**: {topic}

**研究问题**:
{self._format_questions()}

{f"**额外背景**: {context}" if context else ""}

**当前时间**: {datetime.now().strftime("%Y-%m-%d")}

请按照以下步骤进行研究：
1. 首先规划搜索策略，确定关键搜索词
2. 使用web_search工具搜索相关信息
3. 对重要结果使用fetch_webpage获取详细内容
4. 评估信息的可信度和相关度
5. 使用save_finding保存重要发现
6. 根据发现调整研究方向（如需要）
7. 最后使用generate_report生成研究报告

注意：
- 优先搜索2024-2026年的最新信息
- 关注权威来源（学术期刊、知名机构、专业媒体）
- 对重要发现进行交叉验证
- 记录研究的局限性和不确定性
"""

        self.conversation_history = [
            {"role": "user", "content": initial_content}
        ]

        # 执行研究循环
        final_report = None
        for iteration in range(max_iterations):
            self.search_iteration = iteration + 1
            logger.info(f"\n--- Research Iteration {iteration + 1}/{max_iterations} ---")

            try:
                # 调用Claude
                response = await self._call_claude()

                # 处理响应
                result = await self._process_response(response)

                # 检查是否完成
                if result.get("report_generated"):
                    final_report = result.get("report")
                    logger.info("Research completed!")
                    break

                # 检查是否需要用户输入
                if result.get("needs_user_input"):
                    logger.info("Waiting for user input...")
                    break

            except Exception as e:
                logger.error(f"Iteration {iteration + 1} failed: {e}")
                # 添加错误信息到对话
                self.conversation_history.append({
                    "role": "user",
                    "content": f"Error occurred: {str(e)}. Please try a different approach."
                })

        # 构建最终结果
        research_result = {
            "topic": topic,
            "research_questions": self.research_questions,
            "iterations_completed": self.search_iteration,
            "findings": [f.to_dict() for f in self.findings],
            "final_report": final_report,
            "statistics": self._get_statistics(),
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"Research finished with {len(self.findings)} findings")
        return research_result

    def _format_questions(self) -> str:
        """格式化研究问题"""
        if not self.research_questions:
            return "- 该领域的最新研究进展是什么？\n- 有哪些重要的突破或发现？\n- 主要的争议或挑战是什么？"

        return "\n".join([f"- {q}" for q in self.research_questions])

    async def _call_claude(self) -> anthropic.types.Message:
        """调用Claude API"""
        # 获取工具schemas
        tools = self.tool_registry.get_schemas()

        # 调用API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self._get_system_prompt(),
            messages=self.conversation_history,
            tools=tools,
            tool_choice={"type": "auto"}
        )

        return response

    def _get_system_prompt(self) -> str:
        """获取系统提示"""
        return """你是一位专业的科研情报研究助手，专注于生物医学、衰老研究、基因治疗、生物信息学等领域。

## 核心职责
1. **智能搜索规划**: 根据研究目标，制定最优的搜索策略
2. **信息质量评估**: 评估来源的可信度、相关度和时效性
3. **深度内容分析**: 提取关键信息，识别重要发现
4. **交叉验证**: 通过多个独立来源验证关键信息
5. **动态调整**: 根据中间发现调整研究方向

## 评估标准

### 可信度评估 (Credibility)
- **high**: 顶级期刊(Nature/Science/Cell)、知名学术机构、权威数据库
- **medium**: 专业媒体、行业报告、知名博客/公众号
- **low**: 未经验证的来源、营销内容、过时信息

### 相关度评估 (Relevance)
- **high**: 直接回答研究问题、核心相关内容
- **medium**: 部分相关、提供背景信息
- **low**: 边缘相关、参考价值有限

### 证据强度 (Evidence Strength)
- **strong**: 多项独立研究支持、大规模临床试验、meta分析
- **moderate**: 初步研究结果、小规模试验、专家观点
- **weak**: 单一研究、动物实验、推测性结论

## 工作流程
1. 理解研究目标和范围
2. 规划搜索策略（选择合适的关键词组合）
3. 执行搜索并初步筛选结果
4. 深入阅读高价值内容
5. 评估和记录发现
6. 识别知识缺口，调整搜索方向
7. 交叉验证关键发现
8. 生成结构化报告

## 输出要求
- 优先关注2024-2026年的最新研究
- 记录研究的局限性和不确定性
- 标注信息的时效性
- 提供可追溯的来源链接
- 提出合理的后续研究建议

## 重要提醒
- 不要过度依赖单一来源
- 注意区分相关性和因果性
- 警惕夸大宣传和未经验证的声明
- 记录搜索过程中的发现和思考
"""

    async def _process_response(self, response: anthropic.types.Message) -> Dict:
        """处理Claude响应"""
        result = {
            "report_generated": False,
            "needs_user_input": False
        }

        # 添加助手消息到历史
        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({
                    "type": "text",
                    "text": block.text
                })
                logger.info(f"[Claude] {block.text[:200]}...")
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input
                })

        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_content
        })

        # 处理工具调用
        for block in response.content:
            if block.type == "tool_use":
                tool_result = await self.tool_registry.execute(
                    block.name,
                    block.input
                )

                # 添加工具结果
                self.conversation_history.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str)
                        }
                    ]
                })

                # 检查特殊工具
                if block.name == "generate_report":
                    result["report_generated"] = True
                    result["report"] = tool_result

                elif block.name == "request_user_input":
                    result["needs_user_input"] = True

        return result

    def _get_statistics(self) -> Dict:
        """获取研究统计"""
        credibility_dist = {
            "high": len([f for f in self.findings if f.credibility == CredibilityLevel.HIGH]),
            "medium": len([f for f in self.findings if f.credibility == CredibilityLevel.MEDIUM]),
            "low": len([f for f in self.findings if f.credibility == CredibilityLevel.LOW])
        }

        relevance_dist = {
            "high": len([f for f in self.findings if f.relevance == RelevanceLevel.HIGH]),
            "medium": len([f for f in self.findings if f.relevance == RelevanceLevel.MEDIUM]),
            "low": len([f for f in self.findings if f.relevance == RelevanceLevel.LOW])
        }

        return {
            "total_findings": len(self.findings),
            "credibility_distribution": credibility_dist,
            "relevance_distribution": relevance_dist,
            "search_iterations": self.search_iteration
        }

    async def close(self):
        """清理资源"""
        await self.search_engine.close()


# ==================== 使用示例 ====================

async def main():
    # 初始化研究系统
    research_system = AIResearchSystem(
        api_key="your-claude-api-key",
        model="claude-opus-5-5",
        enable_search=True
    )

    # 定义研究主题
    topics = [
        {
            "topic": "NAD+补充剂在抗衰老中的应用和效果",
            "questions": [
                "目前有哪些主要的NAD+补充剂？",
                "人体临床试验的结果如何？",
                "长期使用的安全性数据？",
                "与衰老相关疾病的关系？"
            ]
        },
        {
            "topic": "基因治疗在罕见病治疗中的最新突破",
            "questions": [
                "2024-2025年获批的基因疗法有哪些？",
                "CRISPR技术的临床应用进展？",
                "治疗成本和可及性问题？"
            ]
        }
    ]

    # 执行研究
    for topic_info in topics:
        print(f"\n{'='*70}")
        print(f"Researching: {topic_info['topic']}")
        print(f"{'='*70}\n")

        result = await research_system.research(
            topic=topic_info["topic"],
            research_questions=topic_info["questions"],
            max_iterations=10
        )

        # 保存结果
        output_file = f"research_{topic_info['topic'][:20].replace(' ', '_')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nResults saved to: {output_file}")
        print(f"Total findings: {result['statistics']['total_findings']}")

    await research_system.close()


if __name__ == "__main__":
    asyncio.run(main())
