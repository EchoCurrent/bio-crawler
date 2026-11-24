#!/usr/bin/env python3
"""
AI驱动的智能研究系统 v3.0
使用示例和演示
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加src目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))

from ai_research_system import AIResearchSystem


async def demo_basic_research():
    """基础研究示例"""
    print("=" * 70)
    print("Demo 1: Basic AI-driven Research")
    print("=" * 70)

    # 初始化系统 (需要替换为实际的API key)
    research = AIResearchSystem(
        api_key="your-claude-api-key-here",
        model="claude-opus-5-5",
        enable_search=True  # 启用真实搜索，False则使用模拟数据
    )

    try:
        # 执行研究
        result = await research.research(
            topic="衰老干预的最新研究进展",
            research_questions=[
                "目前最有前景的抗衰老干预措施有哪些？",
                "NAD+补充剂的有效性证据如何？",
                "干细胞疗法在抗衰老中的应用前景？"
            ],
            context="重点关注2024-2026年的最新临床研究",
            max_iterations=5
        )

        # 打印结果
        print("\n" + "=" * 70)
        print("RESEARCH RESULTS")
        print("=" * 70)
        print(f"Topic: {result['topic']}")
        print(f"Iterations: {result['iterations_completed']}")
        print(f"Total Findings: {result['statistics']['total_findings']}")

        print("\n--- Credibility Distribution ---")
        for level, count in result['statistics']['credibility_distribution'].items():
            print(f"  {level}: {count}")

        print("\n--- Top Findings ---")
        for i, finding in enumerate(result['findings'][:5], 1):
            print(f"\n{i}. {finding['topic']}")
            print(f"   Source: {finding['source']}")
            print(f"   Credibility: {finding['credibility']}")
            print(f"   Key Points: {', '.join(finding['key_points'][:3])}")

        # 保存结果
        output_file = f"demo_research_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Results saved to: {output_file}")

    finally:
        await research.close()


async def demo_multi_topic_research():
    """多主题研究示例"""
    print("\n" + "=" * 70)
    print("Demo 2: Multi-Topic Research")
    print("=" * 70)

    research = AIResearchSystem(
        api_key="your-claude-api-key-here",
        model="claude-opus-5-5",
        enable_search=False  # 使用模拟数据演示
    )

    topics = [
        {
            "topic": "基因治疗在罕见病中的应用",
            "questions": [
                "2024-2025年获批的基因疗法？",
                "CRISPR技术的临床进展？",
                "治疗成本问题？"
            ]
        },
        {
            "topic": "细胞疗法在癌症治疗中的突破",
            "questions": [
                "CAR-T疗法的最新进展？",
                "实体瘤治疗的挑战？",
                "联合治疗策略？"
            ]
        }
    ]

    try:
        for topic_info in topics:
            print(f"\n{'-'*70}")
            print(f"Researching: {topic_info['topic']}")
            print(f"{'-'*70}")

            result = await research.research(
                topic=topic_info['topic'],
                research_questions=topic_info['questions'],
                max_iterations=3
            )

            print(f"✅ Completed with {result['statistics']['total_findings']} findings")

    finally:
        await research.close()


async def demo_interactive_research():
    """交互式研究示例 - 模拟用户参与"""
    print("\n" + "=" * 70)
    print("Demo 3: Interactive Research (Simulated)")
    print("=" * 70)

    research = AIResearchSystem(
        api_key="your-claude-api-key-here",
        model="claude-opus-5-5",
        enable_search=False
    )

    try:
        # 第一轮：宽泛研究
        print("\n[Round 1] Broad research on aging...")
        result1 = await research.research(
            topic="抗衰老研究",
            max_iterations=2
        )

        # 模拟用户反馈
        print("\n[User Feedback] Focus more on clinical trials...")

        # 第二轮：基于反馈调整
        print("\n[Round 2] Refined research on clinical trials...")
        result2 = await research.research(
            topic="抗衰老临床试验进展",
            research_questions=[
                "目前处于III期临床试验的抗衰老药物？",
                "临床试验的主要终点指标？"
            ],
            context="Based on previous findings, focus on clinical applications",
            max_iterations=3
        )

        print("\n✅ Interactive research completed")

    finally:
        await research.close()


def print_architecture():
    """打印系统架构"""
    architecture = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                    AI-Driven Research System Architecture                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                    User Interface Layer                             │    ║
║  │         (CLI / API / Web UI / Feishu Bot)                          │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                    │                                         ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                    AI Research System                               │    ║
║  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │    ║
║  │  │   Planner   │  │  Evaluator  │  │  Reporter   │                 │    ║
║  │  │             │  │             │  │             │                 │    ║
║  │  │ • Strategy  │  │ • Credibility│  │ • Synthesize│                │    ║
║  │  │ • Queries   │  │ • Relevance │  │ • Structure │                 │    ║
║  │  │ • Sources   │  │ • Freshness │  │ • Visualize │                 │    ║
║  │  └─────────────┘  └─────────────┘  └─────────────┘                 │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                    │                                         ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                    Tool Registry                                    │    ║
║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │    ║
║  │  │web_search│ │web_fetch │ │save_     │ │generate_ │              │    ║
║  │  │          │ │          │ │finding   │ │report    │              │    ║
║  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │    ║
║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │    ║
║  │  │cross_    │ │adjust_   │ │academic_ │                           │    ║
║  │  │verify    │ │direction │ │search    │                           │    ║
║  │  └──────────┘ └──────────┘ └──────────┘                           │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                    │                                         ║
║  ┌─────────────────────────────────────────────────────────────────────┐    ║
║  │                    External Services                                │    ║
║  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │    ║
║  │  │  Bing    │ │  Baidu   │ │  PubMed  │ │  bioRxiv │              │    ║
║  │  │ Search   │ │ Search   │ │  API     │ │  API     │              │    ║
║  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘              │    ║
║  └─────────────────────────────────────────────────────────────────────┘    ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
    print(architecture)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="AI Research System Demo")
    parser.add_argument('--demo', choices=['basic', 'multi', 'interactive', 'arch'],
                       default='arch', help='Demo to run')
    parser.add_argument('--api-key', help='Claude API Key')

    args = parser.parse_args()

    if args.demo == 'arch':
        print_architecture()
        print("\n💡 To run actual research demos:")
        print("   1. Set your Claude API key: export ANTHROPIC_API_KEY=your-key")
        print("   2. Run: python demo_ai_research.py --demo basic")
        print("   3. Or integrate into your application")

    elif args.demo == 'basic':
        if not args.api_key:
            print("❌ Error: API key required. Use --api-key or set ANTHROPIC_API_KEY")
            return
        # 更新API key
        import ai_research_system
        # 这里需要修改实例化时的key
        await demo_basic_research()

    elif args.demo == 'multi':
        await demo_multi_topic_research()

    elif args.demo == 'interactive':
        await demo_interactive_research()


if __name__ == "__main__":
    asyncio.run(main())
