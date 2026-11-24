#!/usr/bin/env python3
"""
通知推送模块
"""

import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

import httpx
from loguru import logger


class Notifier:
    """通知推送器"""

    def __init__(self, config: Dict):
        self.config = config
        self.console_config = config.get('console', {})
        self.email_config = config.get('email', {})
        self.wecom_config = config.get('wecom', {})

    async def send(self, articles: List[Dict]):
        """发送通知

        Args:
            articles: 文章列表
        """
        if not articles:
            logger.info("没有新文章，跳过通知")
            return

        # 控制台输出
        if self.console_config.get('enabled', True):
            self._send_console(articles)

        # 邮件推送
        if self.email_config.get('enabled', False):
            await self._send_email(articles)

        # 企业微信
        if self.wecom_config.get('enabled', False):
            await self._send_wecom(articles)

    def _send_console(self, articles: List[Dict]):
        """控制台输出"""
        print("\n" + "=" * 70)
        print(f"📰 公众号更新播报 ({len(articles)}篇)")
        print("=" * 70)

        # 按公众号分组
        by_account = {}
        for article in articles:
            account = article.get('account_name', '未知')
            if account not in by_account:
                by_account[account] = []
            by_account[account].append(article)

        for account, items in by_account.items():
            print(f"\n【{account}】({len(items)}篇)")
            print("-" * 50)

            for i, article in enumerate(items, 1):
                title = article.get('title', '无标题')
                summary = article.get('summary', '')
                url = article.get('url', '')
                publish_time = article.get('publish_time', '')

                print(f"\n{i}. {title}")
                if publish_time:
                    print(f"   时间: {publish_time}")
                if summary:
                    print(f"   摘要: {summary[:80]}{'...' if len(summary) > 80 else ''}")
                if url:
                    print(f"   链接: {url}")

                # 图片信息
                local_images = article.get('local_images', [])
                if local_images:
                    print(f"   图片: {len(local_images)}张")

        print("\n" + "=" * 70)
        print(f"共 {len(articles)} 篇新文章")
        print("=" * 70 + "\n")

    async def _send_email(self, articles: List[Dict]):
        """发送邮件"""
        try:
            smtp_host = self.email_config.get('smtp_host')
            smtp_port = self.email_config.get('smtp_port', 587)
            username = self.email_config.get('username')
            password = self.email_config.get('password')
            to_addrs = self.email_config.get('to', [])

            if not all([smtp_host, username, password, to_addrs]):
                logger.warning("邮件配置不完整，跳过邮件推送")
                return

            # 构建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{self.email_config.get('subject_prefix', '[公众号更新]')} {len(articles)}篇新文章"
            msg['From'] = username
            msg['To'] = ", ".join(to_addrs)

            # HTML正文
            html = self._build_email_html(articles)
            msg.attach(MIMEText(html, 'html', 'utf-8'))

            # 发送
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            logger.info(f"邮件已发送给 {len(to_addrs)} 个收件人")

        except Exception as e:
            logger.error(f"邮件发送失败: {e}")

    def _build_email_html(self, articles: List[Dict]) -> str:
        """构建邮件HTML"""
        # 按公众号分组
        by_account = {}
        for article in articles:
            account = article.get('account_name', '未知')
            if account not in by_account:
                by_account[account] = []
            by_account[account].append(article)

        items_html = []

        for account, items in by_account.items():
            items_html.append(f'''
            <div style="margin: 20px 0;">
                <h3 style="color: #07C160; border-bottom: 2px solid #07C160; padding-bottom: 8px;">
                    {account} ({len(items)}篇)
                </h3>
            ''')

            for article in items:
                title = article.get('title', '无标题')
                summary = article.get('summary', '')
                summary_long = article.get('summary_long', '')
                url = article.get('url', '')
                publish_time = article.get('publish_time', '')
                cover_url = article.get('cover_url', '')

                # 转义HTML
                title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                summary = summary.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

                cover_html = f'<img src="{cover_url}" style="max-width: 200px; margin: 10px 0;">' if cover_url else ''

                items_html.append(f'''
                <div style="margin: 15px 0; padding: 15px; background: #f9f9f9; border-left: 4px solid #07C160;">
                    <h4 style="margin: 0 0 10px 0; color: #333;">{title}</h4>
                    {cover_html}
                    <p style="color: #666; font-size: 13px; margin: 5px 0;">
                        {publish_time}
                    </p>
                    <p style="color: #333; line-height: 1.6;">{summary}</p>
                    <a href="{url}" style="color: #07C160; text-decoration: none;">阅读原文 →</a>
                </div>
                ''')

            items_html.append('</div>')

        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>公众号更新</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #07C160;">📰 公众号更新播报</h2>
            <p style="color: #666;">共 {len(articles)} 篇新文章</p>
            {''.join(items_html)}
            <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
            <p style="color: #999; font-size: 12px; text-align: center;">
                本邮件由微信公众号监控系统自动发送
            </p>
        </body>
        </html>
        '''

    async def _send_wecom(self, articles: List[Dict]):
        """发送企业微信消息"""
        try:
            webhook_url = self.wecom_config.get('webhook_url')
            if not webhook_url:
                logger.warning("企业微信webhook未配置")
                return

            # 构建markdown消息
            markdown = self._build_wecom_markdown(articles)

            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": markdown
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()

            logger.info("企业微信消息已发送")

        except Exception as e:
            logger.error(f"企业微信发送失败: {e}")

    def _build_wecom_markdown(self, articles: List[Dict]) -> str:
        """构建企业微信markdown"""
        lines = [f"## 📰 公众号更新播报（{len(articles)}篇）\n"]

        # 按公众号分组
        by_account = {}
        for article in articles:
            account = article.get('account_name', '未知')
            if account not in by_account:
                by_account[account] = []
            by_account[account].append(article)

        for account, items in by_account.items():
            lines.append(f"**【{account}】**")

            for article in items[:3]:  # 每个号最多3条
                title = article.get('title', '无标题')
                summary = article.get('summary', '')[:50]
                url = article.get('url', '')

                lines.append(f"> **{title}**")
                if summary:
                    lines.append(f"> {summary}...")
                if url:
                    lines.append(f"> [阅读原文]({url})")
                lines.append("")

        if len(articles) > 10:
            lines.append(f"... 还有 {len(articles) - 10} 篇，请查看邮件或数据库")

        return "\n".join(lines)
