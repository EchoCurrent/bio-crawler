#!/usr/bin/env python3
"""
飞书通知推送模块
支持文本消息和富文本消息
"""

import asyncio
import json
from typing import Dict, List, Optional

import httpx
from loguru import logger


class FeishuNotifier:
    """飞书机器人通知器"""

    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        """
        Args:
            webhook_url: 飞书机器人Webhook地址
            secret: 可选的签名校验密钥
        """
        self.webhook_url = webhook_url
        self.secret = secret
        self.http = httpx.AsyncClient(timeout=30.0)

    async def send_text(self, content: str) -> bool:
        """发送文本消息"""
        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }

        return await self._send(payload)

    async def send_rich_text(self, title: str, content: List[Dict]) -> bool:
        """
        发送富文本消息

        Args:
            title: 消息标题
            content: 内容块列表，每个元素是 {"tag": "text"/"a"/"at", ...}
        """
        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": content
                    }
                }
            }
        }

        return await self._send(payload)

    async def send_markdown(self, title: str, markdown: str) -> bool:
        """
        发送Markdown格式消息（飞书支持部分Markdown语法）

        Args:
            title: 消息标题
            markdown: Markdown内容
        """
        # 飞书post消息支持简单的markdown-like格式
        # 将markdown转换为飞书的富文本块

        content = self._markdown_to_feishu_blocks(markdown)

        return await self.send_rich_text(title, content)

    def _markdown_to_feishu_blocks(self, markdown: str) -> List[List[Dict]]:
        """将Markdown转换为飞书富文本块"""
        lines = markdown.split('\n')
        blocks = []

        for line in lines:
            if not line.strip():
                continue

            block = []

            # 处理标题
            if line.startswith('# '):
                block.append({"tag": "text", "text": line[2:], "style": ["bold"]})
            elif line.startswith('## '):
                block.append({"tag": "text", "text": line[3:], "style": ["bold"]})
            elif line.startswith('### '):
                block.append({"tag": "text", "text": line[4:], "style": ["bold"]})
            # 处理列表
            elif line.startswith('- ') or line.startswith('* '):
                block.append({"tag": "text", "text": "• " + line[2:]})
            # 处理链接 [text](url)
            elif '[' in line and '](' in line:
                import re
                pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
                matches = re.findall(pattern, line)
                if matches:
                    last_end = 0
                    for text, url in matches:
                        start = line.find(f'[{text}]({url})', last_end)
                        if start > last_end:
                            block.append({"tag": "text", "text": line[last_end:start]})
                        block.append({"tag": "a", "text": text, "href": url})
                        last_end = start + len(f'[{text}]({url})')
                    if last_end < len(line):
                        block.append({"tag": "text", "text": line[last_end:]})
                else:
                    block.append({"tag": "text", "text": line})
            else:
                block.append({"tag": "text", "text": line})

            blocks.append(block)

        return blocks if blocks else [[{"tag": "text", "text": markdown}]]

    async def _send(self, payload: Dict) -> bool:
        """发送请求"""
        try:
            # 如果配置了secret，添加签名
            if self.secret:
                import time
                import hashlib
                import base64

                timestamp = int(time.time())
                string_to_sign = f"{timestamp}\n{self.secret}"
                sign = base64.b64encode(
                    hashlib.sha256(string_to_sign.encode()).digest()
                ).decode()

                payload["timestamp"] = timestamp
                payload["sign"] = sign

            response = await self.http.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            result = response.json()

            if result.get("code") == 0:
                logger.info("飞书消息发送成功")
                return True
            else:
                logger.error(f"飞书消息发送失败: {result.get('msg')}")
                return False

        except Exception as e:
            logger.error(f"飞书消息发送异常: {e}")
            return False

    async def send_research_report(
        self,
        items: List[Dict],
        title: str = "📊 科研情报日报",
        max_items: int = 20
    ) -> bool:
        """
        发送科研情报报告

        Args:
            items: 研究条目列表
            title: 报告标题
            max_items: 最多显示条目数
        """
        if not items:
            logger.info("没有数据，跳过发送")
            return False

        # 构建Markdown内容
        lines = [
            f"**共 {len(items)} 条更新**",
            "",
        ]

        # 按分类分组
        by_category = {}
        for item in items[:max_items]:
            cat = item.get('category', '未分类')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        # 生成分类内容
        for cat, cat_items in by_category.items():
            lines.append(f"**【{cat}】** ({len(cat_items)}条)")
            lines.append("")

            for item in cat_items[:5]:  # 每类最多5条
                title_text = item.get('title', '无标题')[:50]
                source = item.get('source', '未知来源')
                url = item.get('url', '')

                # 验证标记
                verified = item.get('verified', '')
                verify_mark = "✓" if verified == '是' else ""

                lines.append(f"{verify_mark} {title_text}")
                lines.append(f"  来源: {source}")

                if url:
                    lines.append(f"  [链接]({url})")
                lines.append("")

            if len(cat_items) > 5:
                lines.append(f"  ... 还有 {len(cat_items) - 5} 条")
                lines.append("")

        if len(items) > max_items:
            lines.append(f"---")
            lines.append(f"*仅显示前 {max_items} 条，完整数据请查看附件*")

        markdown = '\n'.join(lines)

        return await self.send_markdown(title, markdown)

    async def close(self):
        """关闭HTTP客户端"""
        await self.http.aclose()


class FeishuAppNotifier:
    """飞书应用通知器（通过飞书开放平台API）

    需要配置:
    - app_id: 应用ID
    - app_secret: 应用密钥
    - chat_id: 群聊ID或用户ID
    """

    def __init__(self, app_id: str, app_secret: str, chat_id: str, receive_id_type: Optional[str] = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.chat_id = chat_id
        # 按 ID 前缀自动判断接收者类型: oc_=群聊 ou_=用户open_id
        if receive_id_type:
            self.receive_id_type = receive_id_type
        elif chat_id.startswith("oc_"):
            self.receive_id_type = "chat_id"
        elif chat_id.startswith("ou_"):
            self.receive_id_type = "open_id"
        else:
            self.receive_id_type = "chat_id"
        self.access_token = None
        self.last_message_id = None
        self.http = httpx.AsyncClient(timeout=30.0)

    async def _get_access_token(self) -> str:
        """获取访问令牌"""
        if self.access_token:
            return self.access_token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

        response = await self.http.post(url, json={
            "app_id": self.app_id,
            "app_secret": self.app_secret
        })

        result = response.json()

        if result.get("code") == 0:
            self.access_token = result["tenant_access_token"]
            return self.access_token
        else:
            raise Exception(f"获取飞书token失败: {result.get('msg')}")

    async def send_message(self, msg_type: str, content: Dict) -> bool:
        """发送消息"""
        try:
            token = await self._get_access_token()

            url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={self.receive_id_type}"

            payload = {
                "receive_id": self.chat_id,
                "msg_type": msg_type,
                "content": json.dumps(content)
            }

            response = await self.http.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"}
            )

            result = response.json()

            if result.get("code") == 0:
                self.last_message_id = (result.get("data") or {}).get("message_id")
                logger.info(f"飞书应用消息发送成功 message_id={self.last_message_id}")
                return True
            else:
                logger.error(f"飞书应用消息发送失败 code={result.get('code')}: {result.get('msg')}")
                return False

        except Exception as e:
            logger.error(f"飞书应用消息发送异常: {e}")
            return False

    async def send_text(self, text: str) -> bool:
        """发送文本消息"""
        return await self.send_message("text", {"text": text})

    async def send_interactive_card(self, title: str, elements: List[Dict]) -> bool:
        """
        发送交互式卡片消息

        Args:
            title: 卡片标题
            elements: 卡片元素列表
        """
        card = {
            "config": {
                "wide_screen_mode": True
            },
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                },
                "template": "blue"
            },
            "elements": elements
        }

        return await self.send_message("interactive", card)

    async def send_research_report(
        self,
        items: List[Dict],
        title: str = "📊 科研情报日报",
        max_items: int = 30
    ) -> bool:
        """发送科研情报报告"""
        if not items:
            return False

        # 按分类分组
        by_category = {}
        for item in items[:max_items]:
            cat = item.get('category', '未分类')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        # 构建卡片元素
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**共 {len(items)} 条更新**"
                }
            },
            {"tag": "hr"}
        ]

        for cat, cat_items in by_category.items():
            # 分类标题
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**【{cat}】** ({len(cat_items)}条)"
                }
            })

            # 条目列表
            for item in cat_items[:5]:
                title_text = item.get('title', '无标题')[:40]
                source = item.get('source', '未知')
                url = item.get('url', '')

                verified = item.get('verified', '')
                verify_mark = "✅ " if verified == '是' else ""

                content = f"{verify_mark}**{title_text}**\n📍 {source}"
                if url:
                    content += f"\n🔗 [查看原文]({url})"

                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": content
                    }
                })

                elements.append({"tag": "hr"})

            if len(cat_items) > 5:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"*... 还有 {len(cat_items) - 5} 条*"
                    }
                })

        return await self.send_interactive_card(title, elements)

    async def close(self):
        """关闭HTTP客户端"""
        await self.http.aclose()
