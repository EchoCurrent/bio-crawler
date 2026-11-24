#!/usr/bin/env python3
"""
AI驱动的智能研究助手
使用Claude API + Tool Use，让模型自主控制搜索和信息整理
"""

import asyncio
import json
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

import anthropic
from loguru import logger


@dataclass
class ResearchFinding:
    """研究发现"""
    topic: str
    content: str
    source: str
    url: str
    credibility: str  # high/medium/low
    relevance: str    # high/medium/low
    key_points: List[str]
    follow_up_questions: List[str]


class AIResearchAssistant:
    """AI驱动的研究助手"""

    SYSTEM_PROMPT = """你是一位专业的科研情报研究助手，专注于生物医学、衰老研究、基因治疗等领域。

你的任务是帮助用户深入研究特定主题，通过搜索、分析和交叉验证来获取高质量的信息。

## 工作流程
1. 理解研究目标和范围
2. 规划搜索策略（选择合适的关键词和来源）
3. 执行搜索并评估结果质量
4. 深入阅读重要内容
5. 交叉验证关键信息
6. 整理成结构化报告

## 可用工具
- web_search: 搜索网页信息
- web_fetch: 获取网页详细内容
- save_finding: 保存研究发现
- generate_report: 生成最终报告

## 输出要求
- 优先选择权威来源（学术期刊、知名机构、专业媒体）
- 标注信息可信度和相关度
- 提取关键观点和发现
- 提出后续研究问题
"""

    def __init__(self, api_key: str, model: str = "claude-opus-5-5"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.findings: List[ResearchFinding] = []
        self.conversation_history = []

    async def research(
        self,
        topic: str,
        research_questions: Optional[List[str]] = None,
        max_iterations: int = 10
    ) -> Dict:
        """
        执行AI驱动的研究

        Args:
            topic: 研究主题
            research_questions: 具体研究问题
            max_iterations: 最大迭代次数

        Returns:
            研究结果字典
        """
        logger.info(f"开始AI驱动研究: {topic}")

        # 初始化对话
        initial_message = f"""请帮我深入研究以下主题：

**主题**: {topic}

**研究问题**:
{chr(10).join([f"- {q}" for q in (research_questions or [])]) if research_questions else "- 该领域的最新研究进展是什么？"}
- 有哪些重要的突破或发现？
- 主要的争议或挑战是什么？
- 未来的发展方向如何？

请使用工具搜索相关信息，并整理成结构化的研究报告。
"""

        self.conversation_history = [
            {"role": "user", "content": initial_message}
        ]

        # 执行研究循环
        for iteration in range(max_iterations):
            logger.info(f"研究迭代 {iteration + 1}/{max_iterations}")

            try:
                # 调用Claude API
                response = await self._call_claude()

                # 处理响应
                result = await self._process_response(response)

                # 检查是否完成
                if result.get("completed"):
                    logger.info("研究完成")
                    break

            except Exception as e:
                logger.error(f"迭代 {iteration + 1} 失败: {e}")
                continue

        # 生成最终报告
        final_report = await self._generate_final_report(topic)

        return {
            "topic": topic,
            "findings": [f.__dict__ for f in self.findings],
            "report": final_report,
            "iterations": iteration + 1,
            "timestamp": datetime.now().isoformat()
        }

    async def _call_claude(self) -> anthropic.types.Message:
        """调用Claude API"""
        # 定义工具
        tools = [
            {
                "name": "web_search",
                "description": "搜索网页信息，获取相关研究资料",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最大结果数",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "web_fetch",
                "description": "获取网页详细内容",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "网页URL"
                        }
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "save_finding",
                "description": "保存研究发现",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "content": {"type": "string"},
                        "source": {"type": "string"},
                        "url": {"type": "string"},
                        "credibility": {
                            "type": "string",
                            "enum": ["high", "medium", "low"]
                        },
                        "relevance": {
                            "type": "string",
                            "enum": ["high", "medium", "low"]
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["topic", "content", "source", "url"]
                }
            },
            {
                "name": "generate_report",
                "description": "生成最终研究报告",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "key_findings": {"type": "array", "items": {"type": "string"}},
                        "recommendations": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["summary"]
                }
            }
        ]

        # 调用API
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=self.SYSTEM_PROMPT,
            messages=self.conversation_history,
            tools=tools,
            tool_choice={"type": "auto"}
        )

        return response

    async def _process_response(self, response: anthropic.types.Message) -> Dict:
        """处理Claude响应"""
        result = {"completed": False}

        # 添加助手消息到历史
        self.conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # 处理工具调用
        for block in response.content:
            if block.type == "tool_use":
                tool_result = await self._execute_tool(block.name, block.input)

                # 添加工具结果到历史
                self.conversation_history.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result, ensure_ascii=False)
                        }
                    ]
                })

                # 检查是否生成报告
                if block.name == "generate_report":
                    result["completed"] = True
                    result["report"] = tool_result

        return result

    async def _execute_tool(self, tool_name: str, tool_input: Dict) -> Dict:
        """执行工具"""
        logger.info(f"执行工具: {tool_name}")

        try:
            if tool_name == "web_search":
                return await self._tool_web_search(tool_input)
            elif tool_name == "web_fetch":
                return await self._tool_web_fetch(tool_input)
            elif tool_name == "save_finding":
                return await self._tool_save_finding(tool_input)
            elif tool_name == "generate_report":
                return await self._tool_generate_report(tool_input)
            else:
                return {"error": f"未知工具: {tool_name}"}

        except Exception as e:
            logger.error(f"工具执行失败: {e}")
            return {"error": str(e)}

    async def _tool_web_search(self, params: Dict) -> Dict:
        """网页搜索工具"""
        # 这里可以集成真实的搜索API
        # 目前返回模拟数据

        query = params.get("query", "")
        max_results = params.get("max_results", 10)

        logger.info(f"搜索: {query}")

        # 模拟搜索结果
        mock_results = [
            {
                "title": f"关于{query}的最新研究",
                "url": f"https://example.com/research/{hash(query)}",
                "snippet": f"这是一篇关于{query}的重要研究论文...",
                "source": "Nature"
            }
        ]

        return {
            "results": mock_results[:max_results],
            "query": query,
            "total": len(mock_results)
        }

    async def _tool_web_fetch(self, params: Dict) -> Dict:
        """网页抓取工具"""
        url = params.get("url", "")

        logger.info(f"抓取网页: {url}")

        # 模拟网页内容
        return {
            "url": url,
            "title": "研究文章标题",
            "content": "这是文章的详细内容...",
            "metadata": {
                "author": "张三",
                "date": "2025-01-15",
                "source": "BioArt"
            }
        }

    async def _tool_save_finding(self, params: Dict) -> Dict:
        """保存研究发现"""
        finding = ResearchFinding(
            topic=params.get("topic", ""),
            content=params.get("content", ""),
            source=params.get("source", ""),
            url=params.get("url", ""),
            credibility=params.get("credibility", "medium"),
            relevance=params.get("relevance", "medium"),
            key_points=params.get("key_points", []),
            follow_up_questions=params.get("follow_up_questions", [])
        )

        self.findings.append(finding)
        logger.info(f"保存发现: {finding.topic}")

        return {"status": "saved", "finding_id": len(self.findings) - 1}

    async def _tool_generate_report(self, params: Dict) -> Dict:
        """生成报告"""
        report = {
            "summary": params.get("summary", ""),
            "key_findings": params.get("key_findings", []),
            "recommendations": params.get("recommendations", []),
            "findings_count": len(self.findings)
        }

        logger.info("生成研究报告")
        return report

    async def _generate_final_report(self, topic: str) -> str:
        """生成最终报告"""
        # 基于所有发现生成结构化报告

        high_credibility = [f for f in self.findings if f.credibility == "high"]
        high_relevance = [f for f in self.findings if f.relevance == "high"]

        report = f"""# 研究报告: {topic}

## 执行摘要
基于AI驱动的深入研究，共收集 {len(self.findings)} 条研究发现。

## 关键发现
"""

        for i, finding in enumerate(self.findings[:10], 1):
            report += f"""
### {i}. {finding.topic}
- **来源**: {finding.source}
- **可信度**: {finding.credibility}
- **相关度**: {finding.relevance}
- **关键观点**: {', '.join(finding.key_points[:3])}
- **链接**: {finding.url}
"""

        report += f"""
## 统计信息
- 总发现数: {len(self.findings)}
- 高可信度: {len(high_credibility)}
- 高相关度: {len(high_relevance)}

## 建议后续研究
1. 深入阅读高可信度来源的完整内容
2. 追踪关键研究团队的最新进展
3. 关注相关领域的交叉研究机会
"""

        return report


# 使用示例
async def main():
    # 初始化研究助手
    assistant = AIResearchAssistant(
        api_key="your-claude-api-key",
        model="claude-opus-5-5"
    )

    # 执行研究
    result = await assistant.research(
        topic="衰老干预的最新研究进展",
        research_questions=[
            "目前最有前景的抗衰老药物有哪些？",
            "NAD+补充剂的有效性如何？",
            "干细胞疗法在抗衰老中的应用"
        ],
        max_iterations=5
    )

    # 输出结果
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 保存报告
    with open("research_report.md", "w", encoding="utf-8") as f:
        f.write(result["report"])


if __name__ == "__main__":
    asyncio.run(main())
