#!/usr/bin/env python3
"""
数据库存储模块
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


class Database:
    """SQLite数据库操作类"""

    def __init__(self, db_path: str = "data/wechat.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_conn(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_db(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            # 文章表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    author TEXT,
                    publish_time TEXT,
                    digest TEXT,
                    content_html TEXT,
                    content_text TEXT,
                    summary TEXT,
                    summary_long TEXT,
                    key_points TEXT,  -- JSON
                    tags TEXT,  -- JSON
                    images TEXT,  -- JSON
                    local_images TEXT,  -- JSON
                    cover_url TEXT,
                    word_count INTEGER DEFAULT 0,
                    sentiment TEXT,
                    category TEXT,
                    model_used TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 索引
            conn.execute('CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_articles_account ON articles(account_name)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at)')

            logger.info("数据库初始化完成")

    def article_exists(self, url: str) -> bool:
        """检查文章是否已存在"""
        with self._get_conn() as conn:
            cursor = conn.execute('SELECT 1 FROM articles WHERE url = ?', (url,))
            return cursor.fetchone() is not None

    def save_article(self, article: Dict) -> int:
        """保存文章

        Args:
            article: 文章数据字典

        Returns:
            文章ID
        """
        with self._get_conn() as conn:
            cursor = conn.execute('''
                INSERT OR REPLACE INTO articles (
                    account_name, title, url, author, publish_time, digest,
                    content_html, content_text, summary, summary_long,
                    key_points, tags, images, local_images, cover_url,
                    word_count, sentiment, category, model_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                article.get('account_name', ''),
                article.get('title', ''),
                article.get('url', ''),
                article.get('author'),
                article.get('publish_time'),
                article.get('digest'),
                article.get('content_html'),
                article.get('content_text'),
                article.get('summary'),
                article.get('summary_long'),
                json.dumps(article.get('key_points', []), ensure_ascii=False),
                json.dumps(article.get('tags', []), ensure_ascii=False),
                json.dumps(article.get('images', []), ensure_ascii=False),
                json.dumps(article.get('local_images', []), ensure_ascii=False),
                article.get('cover_url'),
                article.get('word_count', 0),
                article.get('sentiment'),
                article.get('category'),
                article.get('model_used'),
            ))

            article_id = cursor.lastrowid
            logger.debug(f"文章已保存: {article.get('title', '')[:50]}... (ID: {article_id})")
            return article_id

    def get_recent_articles(self, days: int = 1, limit: int = 100) -> List[Dict]:
        """获取最近的文章"""
        with self._get_conn() as conn:
            cursor = conn.execute('''
                SELECT * FROM articles
                WHERE created_at >= datetime('now', ?)
                ORDER BY created_at DESC
                LIMIT ?
            ''', (f'-{days} days', limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_articles_by_account(self, account_name: str, limit: int = 50) -> List[Dict]:
        """获取指定公众号的文章"""
        with self._get_conn() as conn:
            cursor = conn.execute('''
                SELECT * FROM articles
                WHERE account_name = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (account_name, limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_article_by_id(self, article_id: int) -> Optional[Dict]:
        """根据ID获取文章"""
        with self._get_conn() as conn:
            cursor = conn.execute('SELECT * FROM articles WHERE id = ?', (article_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_old_articles(self, days: int = 90) -> int:
        """删除旧文章"""
        with self._get_conn() as conn:
            cursor = conn.execute('''
                DELETE FROM articles
                WHERE created_at < datetime('now', ?)
            ''', (f'-{days} days',))

            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"已删除 {deleted} 篇旧文章")
            return deleted
