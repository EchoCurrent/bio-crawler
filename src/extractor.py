#!/usr/bin/env python3
"""
文章正文提取模块
"""

import asyncio
import hashlib
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup
from loguru import logger
import trafilatura


class ArticleExtractor:
    """文章正文提取器"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.http = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        )

    async def extract_with_browser(self, url: str, crawler) -> Optional[Dict]:
        """使用浏览器提取文章正文（处理搜狗重定向）

        Args:
            url: 搜狗链接或微信文章URL
            crawler: SogouCrawler实例

        Returns:
            包含正文和图片的字典，失败返回None
        """
        if not crawler.context:
            raise RuntimeError("浏览器未启动")

        page = await crawler.context.new_page()

        try:
            logger.debug(f"浏览器访问: {url}")

            # 搜狗链接需要点击而不是直接访问
            if 'weixin.sogou.com/link' in url:
                # 先访问搜索页面
                # 从URL中提取查询词
                import urllib.parse
                parsed = urllib.parse.urlparse(url)
                query = urllib.parse.parse_qs(parsed.query).get('query', [''])[0]

                if query:
                    search_url = f"https://weixin.sogou.com/weixin?type=2&query={urllib.parse.quote(query)}"
                    logger.debug(f"先访问搜索页: {search_url}")
                    await page.goto(search_url, wait_until='networkidle')
                    await asyncio.sleep(2)

                    # 找到对应的链接并点击
                    links = await page.query_selector_all('.news-box li h3 a')
                    if links:
                        # 尝试找到匹配的链接
                        clicked = False
                        for link in links:
                            href = await link.get_attribute('href')
                            if href and url.split('url=')[-1][:30] in href:
                                # 使用evaluate直接导航而不是click
                                await link.evaluate('el => el.removeAttribute("target")')
                                await link.click()
                                clicked = True
                                break

                        if not clicked:
                            # 如果没找到匹配，点击第一个
                            await links[0].evaluate('el => el.removeAttribute("target")')
                            await links[0].click()

                        # 等待跳转到微信文章
                        try:
                            await page.wait_for_url("**mp.weixin.qq.com**", timeout=15000)
                        except:
                            logger.warning("未跳转到微信文章页面")
                            # 截图调试
                            await page.screenshot(path='debug_extract.png')
                            return None
            else:
                # 直接访问微信文章URL
                await page.goto(url, wait_until='networkidle')

            # 获取最终URL
            final_url = page.url
            logger.debug(f"最终URL: {final_url}")

            # 检查是否是微信文章页面
            if 'mp.weixin.qq.com' not in final_url:
                logger.warning(f"不是微信文章页面: {final_url}")
                return None

            # 获取页面内容
            html = await page.content()

            # 解析HTML
            soup = BeautifulSoup(html, 'lxml')

            # 提取元数据
            meta = {
                'title': self._extract_title(soup),
                'author': self._extract_author(soup),
                'account_name': self._extract_account_name(soup),
                'publish_time': self._extract_publish_time(soup),
                'digest': self._extract_digest(soup),
                'url': final_url,  # 使用最终URL
            }

            # 提取正文
            content_html, content_text, images = self._extract_content(soup)

            meta['content_html'] = content_html
            meta['content_text'] = content_text
            meta['images'] = images
            meta['word_count'] = len(content_text) if content_text else 0

            return meta

        except Exception as e:
            logger.error(f"浏览器提取失败 {url}: {e}")
            return None

        finally:
            await page.close()

    async def extract(self, url: str) -> Optional[Dict]:
        """提取文章正文

        Args:
            url: 文章URL

        Returns:
            包含正文和图片的字典，失败返回None
        """
        try:
            # 获取页面
            logger.debug(f"获取页面: {url}")
            response = await self.http.get(url)
            response.raise_for_status()

            # 处理可能的编码问题
            if not response.encoding or response.encoding.lower() == 'iso-8859-1':
                response.encoding = 'utf-8'

            html = response.text

            # 解析HTML
            soup = BeautifulSoup(html, 'lxml')

            # 提取元数据
            meta = {
                'title': self._extract_title(soup),
                'author': self._extract_author(soup),
                'account_name': self._extract_account_name(soup),
                'publish_time': self._extract_publish_time(soup),
                'digest': self._extract_digest(soup),
            }

            # 提取正文
            content_html, content_text, images = self._extract_content(soup)

            meta['content_html'] = content_html
            meta['content_text'] = content_text
            meta['images'] = images
            meta['word_count'] = len(content_text) if content_text else 0

            return meta

        except Exception as e:
            logger.error(f"提取正文失败 {url}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        # 微信文章标题优先级
        selectors = [
            ('meta', {'property': 'og:title'}),
            ('h1', {'id': 'activity-name'}),
            ('h1', {'class': 'rich_media_title'}),
            ('title', {}),
        ]

        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                if tag == 'meta':
                    return el.get('content', '').strip()
                return el.get_text(strip=True)

        return None

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """提取作者"""
        selectors = [
            ('meta', {'property': 'og:article:author'}),
            ('span', {'id': 'js_author_name'}),
            ('span', {'class': 'rich_media_meta rich_media_meta_nickname'}),
        ]

        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                if tag == 'meta':
                    return el.get('content', '').strip()
                return el.get_text(strip=True)

        return None

    def _extract_account_name(self, soup: BeautifulSoup) -> Optional[str]:
        """提取公众号名称"""
        selectors = [
            ('meta', {'property': 'og:article:author'}),
            ('span', {'id': 'js_name'}),
            ('span', {'class': 'rich_media_meta rich_media_meta_nickname'}),
            ('a', {'id': 'js_profile_qrcode'}),
        ]

        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                if tag == 'meta':
                    return el.get('content', '').strip()
                text = el.get_text(strip=True)
                if text:
                    return text

        return None

    def _extract_publish_time(self, soup: BeautifulSoup) -> Optional[str]:
        """提取发布时间"""
        selectors = [
            ('meta', {'property': 'og:article:published_time'}),
            ('em', {'id': 'publish_time'}),
            ('span', {'class': 'rich_media_meta rich_media_meta_text'}),
        ]

        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                if tag == 'meta':
                    return el.get('content', '').strip()
                text = el.get_text(strip=True)
                # 简单验证是否是时间格式
                if re.search(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}', text):
                    return text

        return None

    def _extract_digest(self, soup: BeautifulSoup) -> Optional[str]:
        """提取摘要"""
        selectors = [
            ('meta', {'property': 'og:description'}),
            ('meta', {'name': 'description'}),
        ]

        for tag, attrs in selectors:
            el = soup.find(tag, attrs=attrs)
            if el:
                return el.get('content', '').strip()

        return None

    def _extract_content(self, soup: BeautifulSoup) -> tuple:
        """提取正文内容和图片

        Returns:
            (content_html, content_text, images)
        """
        # 微信文章正文容器
        content_el = (
            soup.find('div', id='js_content') or
            soup.find('div', class_='rich_media_content') or
            soup.find('article') or
            soup.find('div', class_='content')
        )

        if not content_el:
            # 使用trafilatura作为备用
            html = str(soup)
            text = trafilatura.extract(html)
            return "", text or "", []

        # 清理无用元素
        for el in content_el.find_all(['script', 'style', 'iframe']):
            el.decompose()

        # 提取图片
        images = self._extract_images(content_el)

        # 获取HTML和文本
        content_html = str(content_el)
        content_text = content_el.get_text(separator='\n', strip=True)

        return content_html, content_text, images

    def _extract_images(self, content_el) -> List[Dict]:
        """提取图片列表"""
        images = []

        for img in content_el.find_all('img'):
            # 微信图片真实URL在 data-src
            img_url = (
                img.get('data-src') or
                img.get('src') or
                img.get('data-backsrc')
            )

            if not img_url or img_url.startswith('data:'):
                continue

            # 过滤小图标
            if 'icon' in img_url.lower() or 'logo' in img_url.lower():
                continue

            images.append({
                'url': img_url,
                'alt': img.get('alt', ''),
                'width': img.get('data-w') or img.get('width'),
                'height': img.get('data-ratio'),
            })

        return images

    async def download_images(
        self,
        images: List[Dict],
        save_dir: Path,
        article_id: Optional[str] = None
    ) -> List[str]:
        """下载图片

        Args:
            images: 图片列表
            save_dir: 保存目录
            article_id: 文章ID（用于命名）

        Returns:
            本地文件路径列表
        """
        if not images:
            return []

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        local_paths = []

        for i, img in enumerate(images):
            try:
                url = img['url']

                # 生成文件名
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                ext = self._get_image_extension(url)
                prefix = article_id or 'img'
                filename = f"{prefix}_{i:03d}_{url_hash}.{ext}"
                filepath = save_dir / filename

                # 跳过已存在的
                if filepath.exists():
                    local_paths.append(str(filepath))
                    continue

                # 下载
                logger.debug(f"下载图片: {url}")
                response = await self.http.get(url)
                response.raise_for_status()

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                local_paths.append(str(filepath))

            except Exception as e:
                logger.warning(f"图片下载失败 {img.get('url', 'unknown')}: {e}")
                continue

        logger.info(f"下载完成: {len(local_paths)}/{len(images)} 张图片")
        return local_paths

    def _get_image_extension(self, url: str) -> str:
        """从URL获取图片扩展名"""
        # 移除查询参数
        clean_url = url.split('?')[0]
        ext = clean_url.split('.')[-1].lower()

        valid_exts = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']

        if ext in valid_exts:
            return 'jpg' if ext == 'jpeg' else ext

        # 微信图片默认jpg
        return 'jpg'
