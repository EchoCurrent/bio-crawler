#!/usr/bin/env python3
"""
科研情报监控系统 v2.0 - 主程序入口
支持飞书推送、Claude API、Kimi API
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
import yaml

from src.crawler import SogouCrawler
from src.summarizer import KimiSummarizer
from src.bfs_researcher import BFSResearcher, ResearchItem
from src.verifier import CrossVerifier
from src.exporter import DataExporter
from src.storage import Database
from src.feishu_notifier import FeishuNotifier, FeishuAppNotifier


def load_config(config_path: str = "config/sources.yaml") -> dict:
    """加载配置: sources.yaml (可分享) + 本地 secrets.yaml 合并。"""
    from src.config_loader import load_config as _load
    return _load(config_path=config_path)


async def collect_wechat_items(crawler: SogouCrawler, config: dict) -> list:
    """采集公众号线索"""
    items = []

    for account in config.get('wechat_accounts', []):
        if not account.get('enabled', True):
            continue

        logger.info(f"采集公众号: {account['name']}")

        search_queries = account.get('search_queries', [account['name']])
        seen_urls = set()

        for query in search_queries:
            try:
                articles = await crawler.search_articles(query, max_articles=5)

                for article in articles:
                    if article['url'] in seen_urls:
                        continue
                    seen_urls.add(article['url'])

                    item = ResearchItem(
                        title=article['title'],
                        url=article['url'],
                        source=account['name'],
                        source_type="wechat",
                        category=account.get('category', '未分类'),
                        keywords=account.get('keywords', []),
                        publish_time=article.get('publish_time', ''),
                        summary=article.get('digest', '')
                    )
                    items.append(item)

                logger.info(f"  '{query}': 获取 {len(articles)} 条线索")

            except Exception as e:
                logger.error(f"  '{query}' 采集失败: {e}")

    return items


async def send_feishu_notification(items: list, config: dict):
    """发送飞书通知"""
    feishu_config = config.get('feishu', {})

    # 优先使用Webhook方式
    webhook_config = feishu_config.get('webhook', {})
    if webhook_config.get('enabled') and webhook_config.get('url'):
        logger.info("使用飞书Webhook发送通知")
        notifier = FeishuNotifier(
            webhook_url=webhook_config['url'],
            secret=webhook_config.get('secret')
        )

        try:
            success = await notifier.send_research_report(
                items=[item.to_dict() for item in items],
                title=f"📊 科研情报日报 - {datetime.now().strftime('%m月%d日')}"
            )
            if success:
                logger.info("飞书Webhook通知发送成功")
            else:
                logger.error("飞书Webhook通知发送失败")
        finally:
            await notifier.close()
        return

    # 使用飞书应用方式
    app_config = feishu_config.get('app', {})
    if app_config.get('enabled') and app_config.get('app_id'):
        logger.info("使用飞书应用发送通知")
        notifier = FeishuAppNotifier(
            app_id=app_config['app_id'],
            app_secret=app_config['app_secret'],
            chat_id=app_config['chat_id']
        )

        try:
            success = await notifier.send_research_report(
                items=[item.to_dict() for item in items],
                title=f"📊 科研情报日报 - {datetime.now().strftime('%m月%d日')}"
            )
            if success:
                logger.info("飞书应用通知发送成功")
            else:
                logger.error("飞书应用通知发送失败")
        finally:
            await notifier.close()
        return

    logger.info("飞书通知未启用或配置不完整")


async def run_research(config: dict):
    """运行科研情报收集"""
    logger.info("=" * 70)
    logger.info("科研情报监控系统 v2.0")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    # 初始化组件
    db = Database(config['storage']['db_path'])
    crawler = SogouCrawler(
        headless=config['crawler'].get('headless', True),
        delay=config['crawler'].get('request_delay', 3)
    )

    # 选择AI摘要器 (优先Claude， fallback到Kimi)
    summarizer = None
    if config.get('claude', {}).get('enabled'):
        logger.info("使用Claude API进行摘要和验证")
        summarizer = KimiSummarizer(
            api_key=config['claude']['api_key'],
            model=config['claude'].get('model', 'claude-opus-5-5'),
            api_base="https://api.anthropic.com/v1",  # Claude API endpoint
            max_content_length=config['claude'].get('max_tokens', 16000)
        )
    elif config.get('summarizer', {}).get('enabled'):
        logger.info("使用Kimi API进行摘要和验证")
        summarizer = KimiSummarizer(
            api_key=config['summarizer']['api_key'],
            model=config['summarizer'].get('model', 'kimi-k3'),
            api_base=config['summarizer'].get('api_base', 'https://api.moonshot.cn/v1')
        )

    bfs = BFSResearcher(
        max_depth=config['research'].get('max_depth', 2),
        max_results_per_keyword=config['research'].get('max_results', 10)
    )
    verifier = CrossVerifier(summarizer) if summarizer else None
    exporter = DataExporter(config['output'].get('path', 'output'))

    all_items = []

    try:
        await crawler.start()

        # 1. 采集公众号线索
        logger.info("\n【阶段1】采集公众号线索")
        wechat_items = await collect_wechat_items(crawler, config)
        all_items.extend(wechat_items)

        # 2. 广度优先搜索扩展
        logger.info("\n【阶段2】广度优先搜索扩展")
        categories = config.get('categories', {})

        if config['research'].get('max_depth', 0) > 0 and all_items:
            expanded_items = await bfs.research(all_items, categories)
            all_items.extend(expanded_items)

        # 3. 通用关键词直接搜索
        logger.info("\n【阶段3】通用关键词搜索")
        search_keywords = config.get('search_keywords', [])
        if search_keywords:
            direct_items = await bfs.search_direct(search_keywords)
            all_items.extend(direct_items)

        # 4. 去重
        logger.info("\n【阶段4】数据去重")
        seen_urls = set()
        seen_titles = set()
        unique_items = []

        for item in all_items:
            if item.url and item.url in seen_urls:
                continue
            title_key = item.title[:20] if item.title else ""
            if title_key and title_key in seen_titles:
                continue
            if item.url:
                seen_urls.add(item.url)
            if title_key:
                seen_titles.add(title_key)
            unique_items.append(item)

        logger.info(f"去重后: {len(unique_items)} 条 (原始 {len(all_items)} 条)")

        # 5. AI交叉验证
        logger.info("\n【阶段5】AI交叉验证")
        if verifier and config['research'].get('verify', True):
            verify_limit = config['research'].get('verify_sample_size', 50)
            items_to_verify = unique_items[:verify_limit]
            verified_items = await verifier.verify_batch(items_to_verify)
            remaining = unique_items[verify_limit:]
            unique_items = list(verified_items) + remaining
        else:
            logger.info("跳过验证（未启用AI或验证）")

        # 6. AI摘要生成
        logger.info("\n【阶段6】AI摘要生成")
        if summarizer and config['research'].get('summarize', True):
            summarize_limit = config['research'].get('summarize_sample_size', 20)
            items_to_summarize = [i for i in unique_items if not i.summary][:summarize_limit]

            for item in items_to_summarize:
                try:
                    summary = await summarizer.summarize({
                        'title': item.title,
                        'content_text': item.summary or item.title
                    })
                    if summary:
                        item.summary = summary.get('summary_short', '')
                except Exception as e:
                    logger.error(f"摘要生成失败: {e}")

        # 7. 导出
        logger.info("\n【阶段7】导出结果")
        items_dict = [item.to_dict() for item in unique_items]
        output_format = config['output'].get('format', 'csv')

        exported_files = {}
        if config['output'].get('by_category', False):
            exported_files = exporter.export_by_category(items_dict, output_format)
            for cat, path in exported_files.items():
                logger.info(f"  {cat}: {path}")
        else:
            if output_format == 'excel':
                filepath = exporter.export_excel(items_dict)
            elif output_format == 'both':
                filepath = exporter.export_excel(items_dict)
                filepath_csv = exporter.export_csv(items_dict)
                exported_files['csv'] = filepath_csv
            else:
                filepath = exporter.export_csv(items_dict)
            exported_files['main'] = filepath
            logger.info(f"导出: {filepath}")

        # 8. 导出统计
        stats_path = exporter.export_summary_stats(items_dict)

        # 9. 发送飞书通知
        logger.info("\n【阶段8】发送飞书通知")
        await send_feishu_notification(unique_items, config)

        # 10. 保存到数据库
        for item in unique_items:
            try:
                db.save_article(item.to_dict())
            except Exception as e:
                logger.error(f"保存失败: {e}")

        logger.info(f"\n{'=' * 70}")
        logger.info(f"完成: 共处理 {len(unique_items)} 条情报")
        logger.info(f"输出目录: {exporter.output_dir}")
        logger.info("=" * 70)

    finally:
        await crawler.close()
        await bfs.close()


def main():
    parser = argparse.ArgumentParser(description='科研情报监控系统 v2.0')
    parser.add_argument('--config', default='config/sources.yaml', help='配置文件路径')
    parser.add_argument('--output', choices=['csv', 'excel', 'both'], default=None, help='输出格式')
    parser.add_argument('--no-verify', action='store_true', help='跳过AI验证')
    parser.add_argument('--no-summarize', action='store_true', help='跳过AI摘要')
    parser.add_argument('--max-depth', type=int, default=None, help='BFS最大深度')
    parser.add_argument('--send-feishu', action='store_true', help='强制发送飞书通知')

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 命令行覆盖
    if args.output:
        config['output']['format'] = args.output
    if args.no_verify:
        config['research']['verify'] = False
    if args.no_summarize:
        config['research']['summarize'] = False
    if args.max_depth is not None:
        config['research']['max_depth'] = args.max_depth

    # 运行
    asyncio.run(run_research(config))


if __name__ == '__main__':
    main()
