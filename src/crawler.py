#!/usr/bin/env python3
"""
搜狗微信搜索爬虫模块
"""

import asyncio
import random
import re
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger


class SogouCrawler:
    """搜狗微信搜索爬虫"""

    BASE_URL = "https://weixin.sogou.com"

    USER_AGENTS = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    ]

    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def start(self):
        """启动浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ]
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=random.choice(self.USER_AGENTS),
            ignore_https_errors=True,
        )
        logger.info("浏览器已启动")

    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("浏览器已关闭")

    async def _random_delay(self):
        """随机延迟"""
        delay = self.delay + random.uniform(0, 2)
        await asyncio.sleep(delay)

    async def _handle_captcha(self, page: Page) -> bool:
        """处理验证码"""
        captcha_indicators = [
            '.gt_slider_knob',
            '#seccodeImage',
            '.captcha',
            '.verifycode',
            'text=请输入验证码',
            'text=点击按钮开始验证',
        ]

        for indicator in captcha_indicators:
            try:
                if await page.query_selector(indicator):
                    logger.warning("检测到验证码，请手动处理...")
                    # 等待人工处理（最多60秒）
                    for _ in range(60):
                        await asyncio.sleep(1)
                        # 检查验证码是否已消失
                        if not await page.query_selector(indicator):
                            logger.info("验证码已处理")
                            return True
                    logger.error("验证码处理超时")
                    return False
            except:
                continue

        return True

    async def search_accounts(self, keyword: str) -> List[Dict]:
        """搜索公众号

        注意：搜狗微信搜索对公众号搜索(type=1)有反爬限制，
        直接搜索公众号往往返回"暂无相关官方认证订阅号"。
        建议改用 search_articles 搜索文章，或直接使用 get_account_articles_recent。
        """
        if not self.context:
            raise RuntimeError("浏览器未启动，请先调用 start()")

        page = await self.context.new_page()

        try:
            url = f"{self.BASE_URL}/weixin?type=1&query={keyword}"
            logger.debug(f"搜索公众号: {url}")

            await page.goto(url, wait_until='networkidle')
            await self._random_delay()

            # 检查验证码
            if not await self._handle_captcha(page):
                return []

            # 检查是否有"暂无相关"提示
            page_text = await page.evaluate('() => document.body.innerText')
            if '暂无' in page_text or '未找到' in page_text:
                logger.warning(f"搜狗未找到公众号: {keyword}")
                return []

            # 提取公众号列表 - 尝试多种选择器
            accounts = await page.evaluate('''() => {
                // 尝试多种可能的选择器
                const selectors = [
                    '.news-box li',
                    '.results .item',
                    '.account-list .item',
                    '.weixin-account',
                    'ul.news-list li',
                    '.result .item',
                ];

                for (const sel of selectors) {
                    const items = document.querySelectorAll(sel);
                    if (items.length > 0) {
                        return Array.from(items).map(item => {
                            const nameEl = item.querySelector('.tit a, h3 a, .name a, a.title');
                            const wechatIdEl = item.querySelector('.tit .red, .wechat-id, .account');
                            const descEl = item.querySelector('.tit p, .desc, .description');
                            const qrEl = item.querySelector('.ew-pop img, .qrcode img');

                            return {
                                name: nameEl?.innerText?.trim() || '',
                                wechat_id: wechatIdEl?.innerText?.trim() || '',
                                description: descEl?.innerText?.trim() || '',
                                qr_code: qrEl?.src || '',
                                url: nameEl?.href || ''
                            };
                        });
                    }
                }
                return [];
            }''')

            logger.info(f"搜索 '{keyword}': 找到 {len(accounts)} 个公众号")
            return accounts

        except Exception as e:
            logger.error(f"搜索公众号失败: {e}")
            return []

        finally:
            await page.close()

    async def get_account_articles(self, account_name: str, max_articles: int = 10) -> List[Dict]:
        """获取公众号最近文章

        策略：通过搜狗微信文章搜索(type=2)搜索公众号名称，筛选该公众号的文章。
        这比直接搜索公众号更可靠，因为搜狗对公众号搜索有反爬限制。
        """
        if not self.context:
            raise RuntimeError("浏览器未启动，请先调用 start()")

        # 使用文章搜索找到该公众号的文章
        articles = await self.search_articles_by_account(account_name, max_articles)
        return articles

    async def search_articles_by_account(self, account_name: str, max_articles: int = 10) -> List[Dict]:
        """通过文章搜索获取特定公众号的文章"""
        if not self.context:
            raise RuntimeError("浏览器未启动，请先调用 start()")

        page = await self.context.new_page()

        try:
            # 搜索文章，加上公众号名称作为关键词
            url = f"{self.BASE_URL}/weixin?type=2&query={account_name}"
            logger.debug(f"搜索公众号文章: {url}")

            await page.goto(url, wait_until='networkidle')
            await self._random_delay()

            # 检查验证码
            if not await self._handle_captcha(page):
                return []

            # 提取文章列表并筛选
            articles = await page.evaluate('''() => {
                const items = document.querySelectorAll('.news-box li');
                return Array.from(items).map(item => {
                    const titleEl = item.querySelector('h3 a');
                    const accountEl = item.querySelector('.all-time-y2, .s-p span:first-child');
                    const timeEl = item.querySelector('.s2');
                    const digestEl = item.querySelector('.txt-info');
                    const imgEl = item.querySelector('.img-box img');

                    return {
                        title: titleEl?.innerText?.trim() || '',
                        url: titleEl?.href || '',
                        account_name: accountEl?.innerText?.trim() || '',
                        publish_time: timeEl?.innerText?.trim() || '',
                        digest: digestEl?.innerText?.trim() || '',
                        cover_url: imgEl?.src || ''
                    };
                });
            }''')

            # 筛选匹配的公众号（公众号名称可能显示不完全匹配）
            filtered = []
            for article in articles:
                article_account = article.get('account_name', '')
                # 模糊匹配：文章账号包含搜索词或搜索词包含文章账号
                if account_name in article_account or article_account in account_name:
                    filtered.append(article)
                elif len(filtered) < max_articles // 2:  # 如果筛选结果太少，保留一些
                    filtered.append(article)

            logger.info(f"{account_name}: 获取到 {len(filtered)} 篇文章 (原始 {len(articles)} 篇)")
            return filtered[:max_articles]

        except Exception as e:
            logger.error(f"获取文章列表失败: {e}")
            return []

        finally:
            await page.close()

    async def search_articles(self, keyword: str, max_articles: int = 10) -> List[Dict]:
        """搜索文章（按关键词）"""
        if not self.context:
            raise RuntimeError("浏览器未启动，请先调用 start()")

        page = await self.context.new_page()

        try:
            url = f"{self.BASE_URL}/weixin?type=2&query={keyword}"
            logger.debug(f"搜索文章: {url}")

            await page.goto(url, wait_until='networkidle')
            await self._random_delay()

            # 检查验证码
            if not await self._handle_captcha(page):
                return []

            # 提取文章列表
            articles = await page.evaluate('''() => {
                const items = document.querySelectorAll('.news-box li');
                return Array.from(items).map(item => {
                    const titleEl = item.querySelector('h3 a');
                    const accountEl = item.querySelector('.all-time-y2, .s-p span:first-child');
                    const timeEl = item.querySelector('.s2');
                    const digestEl = item.querySelector('.txt-info');
                    const imgEl = item.querySelector('.img-box img');

                    return {
                        title: titleEl?.innerText?.trim() || '',
                        url: titleEl?.href || '',
                        account_name: accountEl?.innerText?.trim() || '',
                        publish_time: timeEl?.innerText?.trim() || '',
                        digest: digestEl?.innerText?.trim() || '',
                        cover_url: imgEl?.src || ''
                    };
                });
            }''')

            logger.info(f"搜索 '{keyword}': 找到 {len(articles)} 篇文章")
            return articles[:max_articles]

        except Exception as e:
            logger.error(f"搜索文章失败: {e}")
            return []

        finally:
            await page.close()

    async def test(self) -> Dict:
        """测试爬虫"""
        await self.start()

        try:
            # 测试搜索公众号
            accounts = await self.search_accounts("三联生活周刊")
            if accounts:
                logger.info(f"测试成功，找到公众号: {accounts[0]['name']}")
                return {"status": "ok", "account": accounts[0]}
            else:
                return {"status": "no_results"}
        finally:
            await self.close()
