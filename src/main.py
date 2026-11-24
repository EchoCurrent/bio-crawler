#!/usr/bin/env python3
"""
微信公众号监控整合系统
主程序入口
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.crawler import SogouCrawler
from src.extractor import ArticleExtractor
from src.summarizer import KimiSummarizer
from src.storage import Database
from src.notifier import Notifier
import yaml


def load_config(config_path: str = "config/accounts.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


async def process_account(
    crawler: SogouCrawler,
    extractor: ArticleExtractor,
    summarizer: KimiSummarizer,
    db: Database,
    account: dict,
    config: dict
) -> list:
    """处理单个公众号"""
    account_name = account['name']
    wechat_id = account.get('wechat_id', '')

    logger.info(f"开始采集: {account_name}")

    try:
        # 1. 搜索公众号并获取文章列表
        articles = await crawler.get_account_articles(wechat_id or account_name)

        if not articles:
            logger.warning(f"{account_name}: 未找到文章")
            return []

        logger.info(f"{account_name}: 发现 {len(articles)} 篇文章")

        # 2. 过滤已采集的文章
        new_articles = []
        for article in articles:
            if not db.article_exists(article['url']):
                new_articles.append(article)

        if not new_articles:
            logger.info(f"{account_name}: 没有新文章")
            return []

        logger.info(f"{account_name}: {len(new_articles)} 篇新文章")

        # 3. 处理每篇文章
        processed = []
        max_articles = config['crawler'].get('max_articles_per_account', 10)

        for article in new_articles[:max_articles]:
            try:
                # 提取正文
                logger.info(f"  提取: {article['title'][:50]}...")
                content = await extractor.extract(article['url'])

                if not content:
                    logger.warning(f"    提取失败")
                    continue

                # 合并数据
                article_data = {
                    **article,
                    **content
                }

                # AI摘要
                if config['summarizer'].get('enabled'):
                    logger.info(f"  生成摘要...")
                    summary = await summarizer.summarize(article_data)
                    if summary:
                        article_data['summary'] = summary.get('summary_short', '')
                        article_data['summary_long'] = summary.get('summary_long', '')
                        article_data['key_points'] = summary.get('key_points', [])
                        article_data['tags'] = summary.get('tags', [])

                # 下载图片
                if config['storage'].get('keep_images'):
                    logger.info(f"  下载图片...")
                    image_dir = Path(config['storage']['image_dir']) / account_name
                    local_images = await extractor.download_images(
                        article_data.get('images', []),
                        image_dir
                    )
                    article_data['local_images'] = local_images

                # 保存到数据库
                db.save_article(article_data)
                processed.append(article_data)

                logger.info(f"    完成")

            except Exception as e:
                logger.error(f"    处理失败: {e}")
                continue

        return processed

    except Exception as e:
        logger.error(f"{account_name}: 采集失败 - {e}")
        return []


async def run_once(config: dict):
    """单次运行"""
    logger.info("=" * 60)
    logger.info("微信公众号监控整合系统")
    logger.info(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 初始化组件
    db = Database(config['storage']['db_path'])
    crawler = SogouCrawler(
        headless=config['crawler'].get('headless', True),
        delay=config['crawler'].get('request_delay', 3)
    )
    extractor = ArticleExtractor()
    summarizer = KimiSummarizer(
        api_key=config['summarizer'].get('api_key'),
        model=config['summarizer'].get('model', 'kimi-k3'),
        api_base=config['summarizer'].get('api_base', 'https://api.moonshot.cn/v1')
    )
    notifier = Notifier(config['notifier'])

    all_articles = []

    try:
        # 启动浏览器
        await crawler.start()

        # 处理核心公众号
        logger.info("\n【核心公众号】")
        for account in config.get('core_accounts', []):
            if not account.get('enabled', True):
                continue
            articles = await process_account(crawler, extractor, summarizer, db, account, config)
            all_articles.extend(articles)

        # 处理相关公众号
        logger.info("\n【相关公众号】")
        for account in config.get('related_accounts', []):
            if not account.get('enabled', True):
                continue
            articles = await process_account(crawler, extractor, summarizer, db, account, config)
            all_articles.extend(articles)

    finally:
        await crawler.close()

    # 发送通知
    logger.info(f"\n{'=' * 60}")
    logger.info(f"采集完成: 共 {len(all_articles)} 篇新文章")

    if all_articles:
        await notifier.send(all_articles)
        logger.info("通知已发送")
    else:
        logger.info("没有新文章，跳过通知")

    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='微信公众号监控整合系统')
    parser.add_argument('--once', action='store_true', help='单次运行')
    parser.add_argument('--config', default='config/accounts.yaml', help='配置文件路径')
    parser.add_argument('--init-db', action='store_true', help='初始化数据库')

    args = parser.parse_args()

    # 初始化日志
    logger.add(
        "logs/wechat_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="30 days",
        encoding="utf-8"
    )

    # 加载配置
    config = load_config(args.config)

    # 初始化数据库
    if args.init_db:
        from scripts.init_db import main as init_db
        init_db()
        return

    # 单次运行
    if args.once:
        asyncio.run(run_once(config))
        return

    # 默认单次运行（后续可扩展为定时任务）
    logger.info("提示: 使用 --once 参数运行单次采集，或配置定时任务")
    asyncio.run(run_once(config))


if __name__ == '__main__':
    main()
