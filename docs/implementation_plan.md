# 微信公众号监控整合系统 - 实现方案分析

## 项目背景
- **目标**: 追踪特定公众号更新，自动提取推文内容
- **整合需求**: 结构化存储、AI摘要、图片归档、推送通知
- **约束条件**: 不使用微信个人号登录（避免封号风险），优先公开数据方案

---

## 一、数据来源方案对比

### 方案A: 搜狗微信搜索（推荐）
**原理**: 搜狗与微信合作的历史遗留接口，可搜索公众号和文章

| 维度 | 评估 |
|------|------|
| 数据覆盖 | 大部分公众号，但新号/小号可能缺失 |
| 实时性 | 通常延迟数小时到1天 |
| 反爬强度 | 中等，需要IP池+UA轮换 |
| 成本 | 免费 |
| 风险 | 无账号风险，纯公开数据 |

**关键接口**:
- 公众号搜索: `https://weixin.sogou.com/weixin?type=1&query=公众号名`
- 文章搜索: `https://weixin.sogou.com/weixin?type=2&query=关键词`

### 方案B: 微信公众平台公开接口（备选）
**原理**: 通过公众号的公开历史消息页面获取

| 维度 | 评估 |
|------|------|
| 数据覆盖 | 仅已关注/可查看的公众号 |
| 实时性 | 实时 |
| 反爬强度 | 高，需要有效cookie+token |
| 成本 | 需要小号（风险账号） |
| 风险 | 需要登录态，有一定风险 |

### 方案C: 第三方数据平台（省心方案）
**推荐平台**: 新榜、清博、西瓜数据、微小宝

| 维度 | 评估 |
|------|------|
| 数据覆盖 | 全量，最全 |
| 实时性 | 实时~分钟级 |
| 反爬强度 | 无（官方API） |
| 成本 | ¥500-5000/月 |
| 风险 | 无 |

---

## 二、系统架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    调度层 (Scheduler)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 定时任务     │  │ 增量去重    │  │ 失败重试/告警       │  │
│  │ (APScheduler)│  │ (Redis/DB)  │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    采集层 (Crawler)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 搜狗微信    │  │ 公众号RSS   │  │ 备用: 第三方API     │  │
│  │ 搜索爬虫    │  │ 转换器      │  │                     │  │
│  │ (Playwright)│  │ (WeRSS等)   │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    处理层 (Processor)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 正文提取    │  │ 图片下载    │  │ AI摘要生成          │  │
│  │ (trafilatura)│  │ (OSS/本地)  │  │ (Claude/Kimi API)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    存储层 (Storage)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 文章表      │  │ 图片表      │  │ 摘要/标签表         │  │
│  │ (PostgreSQL)│  │ (MinIO/FS)  │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    推送层 (Notifier)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ 邮件        │  │ 企业微信    │  │ Webhook/钉钉        │  │
│  │ (SMTP)      │  │ 机器人      │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详细设计

### 3.1 数据模型 (SQLAlchemy)

```python
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class OfficialAccount(Base):
    """公众号信息表"""
    __tablename__ = "official_accounts"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, comment="公众号名称")
    wechat_id = Column(String(64), unique=True, comment="微信号")
    description = Column(Text, comment="简介")
    avatar_url = Column(String(512), comment="头像URL")
    qr_code_url = Column(String(512), comment="二维码")
    
    # 采集配置
    source = Column(String(32), default="sogou", comment="采集来源")
    is_active = Column(Boolean, default=True)
    last_crawled_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Article(Base):
    """文章主表"""
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("official_accounts.id"), index=True)
    
    # 微信侧标识
    msg_id = Column(String(128), unique=True, index=True, comment="微信消息ID")
    sn = Column(String(128), comment="微信sn参数")
    
    # 内容
    title = Column(String(256), index=True)
    author = Column(String(128), nullable=True)
    digest = Column(Text, comment="摘要")
    content_html = Column(Text, comment="原始HTML")
    content_text = Column(Text, comment="纯文本")
    cover_url = Column(String(512), comment="封面图")
    
    # 媒体
    images = Column(JSON, default=list, comment="图片URL列表")
    local_images = Column(JSON, default=list, comment="本地图片路径")
    
    # 元数据
    publish_time = Column(DateTime, index=True)
    read_count = Column(Integer, nullable=True)
    like_count = Column(Integer, nullable=True)
    
    # 处理状态
    is_processed = Column(Boolean, default=False, comment="是否已提取正文")
    is_summarized = Column(Boolean, default=False, comment="是否已生成摘要")
    is_notified = Column(Boolean, default=False, comment="是否已推送")
    
    created_at = Column(DateTime, default=datetime.utcnow)

class ArticleSummary(Base):
    """AI摘要表"""
    __tablename__ = "article_summaries"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), unique=True)
    
    summary_short = Column(Text, comment="一句话摘要")
    summary_long = Column(Text, comment="详细摘要")
    key_points = Column(JSON, default=list, comment="要点列表")
    tags = Column(JSON, default=list, comment="标签")
    sentiment = Column(String(32), comment="情感倾向")
    
    model_used = Column(String(64), comment="使用的模型")
    generated_at = Column(DateTime, default=datetime.utcnow)
```

### 3.2 采集模块 - 搜狗微信爬虫

```python
import asyncio
import re
import json
from typing import List, Dict, Optional
from playwright.async_api import async_playwright
from dataclasses import dataclass

@dataclass
class ArticleMeta:
    """文章元数据"""
    title: str
    url: str
    account_name: str
    publish_time: Optional[str]
    digest: str
    cover_url: str

class SogouWechatCrawler:
    """搜狗微信搜索爬虫"""
    
    BASE_URL = "https://weixin.sogou.com"
    
    def __init__(self, proxy_pool: Optional[List[str]] = None):
        self.proxy_pool = proxy_pool or []
        self.browser = None
        self.context = None
    
    async def __aenter__(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        return self
    
    async def __aexit__(self, *args):
        await self.browser.close()
    
    async def search_articles(self, keyword: str, page: int = 1) -> List[ArticleMeta]:
        """搜索公众号文章"""
        url = f"{self.BASE_URL}/weixin?type=2&query={keyword}&page={page}"
        page_obj = await self.context.new_page()
        
        try:
            await page_obj.goto(url, wait_until='networkidle')
            
            # 处理可能的验证码
            if await self._has_captcha(page_obj):
                await self._handle_captcha(page_obj)
            
            # 提取文章列表
            articles = await page_obj.evaluate('''() => {
                const items = document.querySelectorAll('.news-box li');
                return Array.from(items).map(item => {
                    const titleEl = item.querySelector('h3 a');
                    const accountEl = item.querySelector('.account');
                    const timeEl = item.querySelector('.s2');
                    const digestEl = item.querySelector('.txt-info');
                    const imgEl = item.querySelector('.img-box img');
                    
                    return {
                        title: titleEl?.innerText?.trim() || '',
                        url: titleEl?.href || '',
                        account: accountEl?.innerText?.trim() || '',
                        publish_time: timeEl?.innerText?.trim() || '',
                        digest: digestEl?.innerText?.trim() || '',
                        cover_url: imgEl?.src || ''
                    };
                });
            }''')
            
            return [ArticleMeta(**a) for a in articles]
            
        finally:
            await page_obj.close()
    
    async def get_account_articles(self, account_wechat_id: str) -> List[ArticleMeta]:
        """获取特定公众号的最新文章"""
        # 先搜索公众号
        search_url = f"{self.BASE_URL}/weixin?type=1&query={account_wechat_id}"
        page_obj = await self.context.new_page()
        
        try:
            await page_obj.goto(search_url, wait_until='networkidle')
            
            # 点击公众号进入文章列表
            account_link = await page_obj.query_selector('.tit a')
            if account_link:
                async with self.context.expect_page() as new_page_info:
                    await account_link.click()
                article_page = await new_page_info.value
                await article_page.wait_for_load_state('networkidle')
                
                # 提取文章列表
                articles = await article_page.evaluate('''() => {
                    // 公众号历史消息页面结构
                    const items = document.querySelectorAll('.weui_media_box');
                    return Array.from(items).map(item => ({
                        title: item.querySelector('.weui_media_title')?.innerText?.trim(),
                        url: item.querySelector('.weui_media_title')?.href,
                        publish_time: item.querySelector('.weui_media_desc')?.innerText?.trim(),
                        digest: item.querySelector('.weui_media_desc')?.innerText?.trim(),
                        cover_url: item.querySelector('.weui_media_hd img')?.src || ''
                    }));
                }''')
                
                await article_page.close()
                return [ArticleMeta(**a) for a in articles]
            
            return []
            
        finally:
            await page_obj.close()
    
    async def _has_captcha(self, page) -> bool:
        """检测是否出现验证码"""
        captcha_selectors = ['.gt_slider_knob', '#seccodeImage', '.captcha']
        for selector in captcha_selectors:
            if await page.query_selector(selector):
                return True
        return False
    
    async def _handle_captcha(self, page):
        """处理验证码 - 可接入打码平台"""
        # 方案1: 人工处理（开发阶段）
        # 方案2: 接入打码平台（超级鹰、图鉴等）
        # 方案3: 切换IP重试
        print("[!] 检测到验证码，需要处理")
        # 这里可以接入打码平台API
        pass
```

### 3.3 正文提取模块

```python
import trafilatura
import httpx
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
import os
import hashlib
from pathlib import Path

class ArticleProcessor:
    """文章处理器"""
    
    def __init__(self, image_storage_path: str = "./data/images"):
        self.image_storage_path = Path(image_storage_path)
        self.image_storage_path.mkdir(parents=True, exist_ok=True)
        self.http = httpx.AsyncClient(timeout=30.0)
    
    async def extract_content(self, url: str) -> Optional[Dict]:
        """提取文章正文和图片"""
        try:
            # 获取页面
            response = await self.http.get(url, follow_redirects=True)
            response.raise_for_status()
            html = response.text
            
            # 使用trafilatura提取正文
            text = trafilatura.extract(html, include_comments=False, 
                                      include_tables=True, no_fallback=False)
            
            # 解析HTML提取结构化数据
            soup = BeautifulSoup(html, 'lxml')
            
            # 提取微信特有的元数据
            meta = {
                'title': self._extract_title(soup),
                'author': self._extract_author(soup),
                'publish_time': self._extract_publish_time(soup),
                'account_name': self._extract_account_name(soup),
                'content_html': self._extract_content_html(soup),
                'content_text': text,
                'images': self._extract_images(soup)
            }
            
            return meta
            
        except Exception as e:
            print(f"[!] 提取失败 {url}: {e}")
            return None
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        # 微信文章标题在 og:title 或 #activity-name
        og_title = soup.find('meta', property='og:title')
        if og_title:
            return og_title.get('content')
        
        title_el = soup.select_one('#activity-name')
        return title_el.get_text(strip=True) if title_el else None
    
    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """提取作者"""
        author_el = soup.select_one('#js_name')
        return author_el.get_text(strip=True) if author_el else None
    
    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[str]:
        """提取发布时间"""
        time_el = soup.select_one('#publish_time')
        return time_el.get_text(strip=True) if time_el else None
    
    def _extract_account_name(self, soup: BeautifulSoup) -> Optional[str]:
        """提取公众号名称"""
        # 通常在 js_account_name 或 profile_nickname
        for selector in ['#js_account_name', '.profile_nickname', 'meta[property="og:article:author"]']:
            el = soup.select_one(selector)
            if el:
                return el.get('content') if el.name == 'meta' else el.get_text(strip=True)
        return None
    
    def _extract_content_html(self, soup: BeautifulSoup) -> str:
        """提取正文HTML"""
        content_el = soup.select_one('#js_content')
        return str(content_el) if content_el else ""
    
    def _extract_images(self, soup: BeautifulSoup) -> List[Dict]:
        """提取图片列表"""
        images = []
        content_el = soup.select_one('#js_content')
        if not content_el:
            return images
        
        for img in content_el.find_all('img'):
            # 微信图片真实URL在 data-src
            img_url = img.get('data-src') or img.get('src')
            if img_url and not img_url.startswith('data:'):
                images.append({
                    'url': img_url,
                    'alt': img.get('alt', ''),
                    'width': img.get('data-w'),
                    'height': img.get('data-ratio', '')  # 微信用比例表示高度
                })
        
        return images
    
    async def download_image(self, url: str, article_id: str) -> Optional[str]:
        """下载图片到本地"""
        try:
            response = await self.http.get(url, follow_redirects=True)
            response.raise_for_status()
            
            # 生成文件名
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            ext = url.split('?')[0].split('.')[-1] or 'jpg'
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'
            
            filename = f"{article_id}_{url_hash}.{ext}"
            filepath = self.image_storage_path / filename
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            return str(filepath)
            
        except Exception as e:
            print(f"[!] 图片下载失败 {url}: {e}")
            return None
```

### 3.4 AI摘要模块

```python
import anthropic
import json
from typing import List, Dict, Optional

class AISummarizer:
    """AI摘要生成器"""
    
    PROMPT_TEMPLATE = """请对以下微信公众号文章进行分析，输出JSON格式结果：

标题: {title}
作者: {author}
发布时间: {publish_time}

正文:
{content}

请输出以下JSON结构:
{{
    "summary_short": "一句话概括核心观点（50字内）",
    "summary_long": "详细摘要（200-300字）",
    "key_points": ["要点1", "要点2", "要点3", ...],
    "tags": ["标签1", "标签2", ...],
    "sentiment": "positive|neutral|negative",
    "category": "科技|商业|生活|娱乐|..."
}}"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5-5"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
    
    async def summarize(self, article: Dict) -> Optional[Dict]:
        """生成文章摘要"""
        try:
            content = article.get('content_text', '')[:8000]  # 限制长度
            
            prompt = self.PROMPT_TEMPLATE.format(
                title=article.get('title', ''),
                author=article.get('author', ''),
                publish_time=article.get('publish_time', ''),
                content=content
            )
            
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # 解析JSON
            result_text = response.content[0].text
            # 提取JSON部分（可能被markdown包裹）
            json_match = self._extract_json(result_text)
            
            if json_match:
                result = json.loads(json_match)
                result['model_used'] = self.model
                return result
            
        except Exception as e:
            print(f"[!] 摘要生成失败: {e}")
            return None
    
    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取JSON"""
        import re
        
        # 尝试匹配markdown code block
        code_block = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if code_block:
            return code_block.group(1)
        
        # 尝试匹配花括号
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)
        
        return None
    
    async def batch_summarize(self, articles: List[Dict], batch_size: int = 5) -> List[Dict]:
        """批量生成摘要"""
        results = []
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i+batch_size]
            batch_results = await asyncio.gather(*[self.summarize(a) for a in batch])
            results.extend(batch_results)
        return results
```

### 3.5 通知模块

```python
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional

class Notifier:
    """通知推送器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.http = httpx.AsyncClient(timeout=30.0)
    
    async def send_wecom(self, articles: List[Dict]) -> bool:
        """企业微信机器人推送"""
        webhook_url = self.config.get('wecom_webhook')
        if not webhook_url:
            return False
        
        # 构建markdown消息
        markdown_content = self._build_wecom_markdown(articles)
        
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content
            }
        }
        
        try:
            response = await self.http.post(webhook_url, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"[!] 企业微信推送失败: {e}")
            return False
    
    def _build_wecom_markdown(self, articles: List[Dict]) -> str:
        """构建企业微信markdown"""
        lines = [f"## 📰 公众号更新播报（{len(articles)}篇）\n"]
        
        for article in articles[:10]:  # 最多10条
            title = article.get('title', '无标题')
            account = article.get('account_name', '未知')
            summary = article.get('summary_short', '')[:50]
            url = article.get('url', '')
            
            lines.append(f"**{title}**")
            lines.append(f"> 公众号: {account}")
            if summary:
                lines.append(f"> 摘要: {summary}...")
            if url:
                lines.append(f"> [阅读原文]({url})")
            lines.append("")
        
        return "\n".join(lines)
    
    async def send_email(self, articles: List[Dict], recipients: List[str]) -> bool:
        """邮件推送"""
        smtp_config = self.config.get('smtp', {})
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"公众号更新 - {len(articles)}篇新文章"
        msg['From'] = smtp_config.get('from')
        msg['To'] = ", ".join(recipients)
        
        # HTML正文
        html = self._build_email_html(articles)
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        
        try:
            with smtplib.SMTP(smtp_config['host'], smtp_config['port']) as server:
                server.starttls()
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[!] 邮件发送失败: {e}")
            return False
    
    def _build_email_html(self, articles: List[Dict]) -> str:
        """构建邮件HTML"""
        # 使用Jinja2模板更优雅，这里简化
        items = []
        for article in articles:
            items.append(f"""
            <div style="margin: 20px 0; padding: 15px; border-left: 4px solid #07C160;">
                <h3 style="margin: 0 0 10px 0;">{article.get('title')}</h3>
                <p style="color: #666; font-size: 14px; margin: 5px 0;">
                    {article.get('account_name')} | {article.get('publish_time')}
                </p>
                <p style="color: #333;">{article.get('summary_short', '')}</p>
                <a href="{article.get('url')}" style="color: #07C160;">阅读原文 →</a>
            </div>
            """)
        
        return f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #07C160;">📰 公众号更新</h2>
            {''.join(items)}
        </body>
        </html>
        """
```

---

## 四、部署方案

### 4.1 技术栈选择

| 组件 | 推荐方案 | 备选 |
|------|---------|------|
| 爬虫框架 | Playwright (Python) | Scrapy + Selenium |
| 任务调度 | APScheduler | Celery + Redis |
| 数据库 | PostgreSQL | SQLite (开发) / MySQL |
| 对象存储 | MinIO (自建) | 阿里云OSS / AWS S3 |
| AI接口 | Claude API | Kimi / 文心一言 |
| 部署 | Docker Compose | Kubernetes |

### 4.2 Docker Compose 配置

```yaml
version: '3.8'

services:
  # 主应用
  wechat-crawler:
    build: .
    container_name: wechat-crawler
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/wechat
      - REDIS_URL=redis://redis:6379/0
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - db
      - redis
    restart: unless-stopped
  
  # 数据库
  db:
    image: postgres:15-alpine
    container_name: wechat-db
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=wechat
    restart: unless-stopped
  
  # 缓存/队列
  redis:
    image: redis:7-alpine
    container_name: wechat-redis
    volumes:
      - redis_data:/data
    restart: unless-stopped
  
  # 对象存储（图片）
  minio:
    image: minio/minio:latest
    container_name: wechat-minio
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    environment:
      - MINIO_ROOT_USER=admin
      - MINIO_ROOT_PASSWORD=password
    ports:
      - "9000:9000"
      - "9001:9001"
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

### 4.3 项目目录结构

```
wechat-crawler/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── config/
│   ├── settings.yaml          # 配置文件
│   └── accounts.yaml          # 监控的公众号列表
├── src/
│   ├── __init__.py
│   ├── main.py                # 入口
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── sogou.py           # 搜狗爬虫
│   │   └── wechat.py          # 微信官方接口（备用）
│   ├── processor/
│   │   ├── __init__.py
│   │   ├── extractor.py       # 正文提取
│   │   ├── image.py           # 图片处理
│   │   └── summarizer.py      # AI摘要
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py        # SQLAlchemy
│   │   └── models.py          # 数据模型
│   ├── notifier/
│   │   ├── __init__.py
│   │   ├── wecom.py           # 企业微信
│   │   ├── email.py           # 邮件
│   │   └── webhook.py         # Webhook
│   └── utils/
│       ├── __init__.py
│       ├── proxy.py           # 代理池
│       └── logger.py          # 日志
├── scripts/
│   ├── init_db.py             # 初始化数据库
│   └── test_crawler.py        # 测试爬虫
├── data/                      # 数据目录（gitignore）
└── tests/
    ├── test_crawler.py
    ├── test_extractor.py
    └── test_summarizer.py
```

---

## 五、实施路线图

### Phase 1: MVP (1-2天)
- [ ] 搭建项目骨架和数据库
- [ ] 实现搜狗微信基础爬虫
- [ ] 文章URL -> 正文提取
- [ ] 命令行输出结果

### Phase 2: 核心功能 (2-3天)
- [ ] 图片下载和本地存储
- [ ] AI摘要集成
- [ ] 企业微信/邮件推送
- [ ] 定时任务调度

### Phase 3: 健壮性 (2-3天)
- [ ] 代理池和反爬策略
- [ ] 失败重试和告警
- [ ] 数据去重和增量更新
- [ ] Web管理界面（可选）

### Phase 4: 优化扩展
- [ ] 多源采集（RSS、第三方API）
- [ ] 全文搜索（Elasticsearch）
- [ ] 统计分析报表
- [ ] 多用户/权限管理

---

## 六、风险与合规提醒

| 风险 | 等级 | 应对措施 |
|------|------|---------|
| 搜狗反爬升级 | 中 | 多源采集，降低频率，用户代理轮换 |
| 微信文章URL失效 | 低 | 及时下载归档，不依赖在线URL |
| 版权风险 | **高** | 仅用于个人学习/研究，勿大规模传播 |
| 数据隐私 | 中 | 不采集用户隐私数据，仅公开文章 |
| 服务稳定性 | 低 | 容器化部署，自动重启，健康检查 |

> **重要合规提示**:
> 1. 微信公众号文章有版权保护，批量采集需获得授权或仅限于个人合理使用范围
> 2. 遵守《网络安全法》和《数据安全法》，不采集、存储敏感个人信息
> 3. 控制采集频率，避免对目标网站造成压力
> 4. 如需商用，建议购买新榜等官方数据服务

---

## 七、下一步建议

1. **确认需求细节**:
   - 监控多少个公众号？
   - 更新频率要求？（实时/小时级/天级）
   - 推送渠道偏好？（企业微信/邮件/钉钉）

2. **准备环境**:
   - 服务器或本地运行？
   - 数据库选择？
   - AI API key？

3. **快速验证**:
   - 先写个简单脚本测试搜狗搜索是否可用
   - 确认目标公众号在搜狗微信的覆盖情况

---

这个方案基于**纯公开数据**，无需登录微信账号，风险可控。如果你确认方向，我可以开始搭建项目骨架。