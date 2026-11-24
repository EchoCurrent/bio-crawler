# 科研情报监控系统 - 实现方案

## 需求确认 (2026-11-23 更新)

| 维度 | 确认结果 |
|------|---------|
| **核心目标** | 监控BioScience领域公众号+网站，交叉验证，多源整合 |
| **数据源** | 搜狗微信搜索（线索）+ 通用搜索引擎（百度/必应/Google）验证 |
| **关注领域** | 医疗/BioArt、衰老/aging、生物谷、ckbiobank.org |
| **整理形式** | 事件聚合、主题日报/周报、关键词追踪、原文转载+来源标注 |
| **输出格式** | Excel/CSV |
| **验证深度** | 简单验证（2-3个独立源） |
| **AI辅助** | 广度优先搜索遍历 + AI整理 |

---

## 系统架构 v2.0

```
┌─────────────────────────────────────────────────────────────────┐
│                     配置层 (Config)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 监控源配置   │  │ 领域分类     │  │ 关键词追踪               │  │
│  │ (公众号/网站)│  │ (自定义)     │  │ ( BioScience相关词)      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     采集层 (Collectors)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 搜狗微信     │  │ 网站RSS     │  │ 通用搜索引擎             │  │
│  │ 公众号线索   │  │ (BioArt等)  │  │ (百度/必应/Google)       │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     处理层 (Processor)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ 广度优先搜索 │  │ AI交叉验证  │  │ 事件聚合                 │  │
│  │ (BFS遍历)    │  │ (Kimi)      │  │ (多源对比)               │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     输出层 (Output)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Excel/CSV   │  │ 主题日报    │  │ 控制台通知               │  │
│  │ (结构化数据) │  │ (可选)      │  │                          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心模块设计

### 1. 监控源配置 (config/sources.yaml)

```yaml
# 监控源配置

# 微信公众号 (通过搜狗搜索获取线索)
wechat_accounts:
  - name: "BioArt"
    keywords: ["BioArt", "生物艺术"]
    category: "生物医学"
    enabled: true
  - name: "aging"
    keywords: ["aging", "衰老", "抗衰老"]
    category: "衰老研究"
    enabled: true
  - name: "生物谷"
    keywords: ["生物谷", "生物医药"]
    category: "生物医药"
    enabled: true

# 网站监控
websites:
  - name: "CK Biobank"
    url: "https://www.ckbiobank.org/"
    rss: null  # 如果有RSS则填写
    keywords: ["biobank", "cohort", "队列"]
    category: "生物样本库"
    enabled: true
  - name: "BioArt"
    url: "https://www.bioart.org.cn/"
    rss: "https://www.bioart.org.cn/feed"
    keywords: ["BioArt", "生物医学"]
    category: "生物医学"
    enabled: true

# 通用搜索关键词 (用于交叉验证)
search_keywords:
  - "BioArt 最新研究"
  - "衰老 研究进展"
  - "biobank cohort study"
  - "基因治疗 breakthrough"

# 领域分类 (可自定义扩展)
categories:
  生物医学:
    keywords: ["基因", "细胞", "蛋白", "药物", "临床试验"]
  衰老研究:
    keywords: ["衰老", "长寿", "抗衰老", "sirtuin", "NAD+"]
  生物医药:
    keywords: ["创新药", "生物制剂", "疫苗", "抗体"]
  生物样本库:
    keywords: ["biobank", "cohort", "队列", "样本库"]

# 输出配置
output:
  format: "csv"  # csv/excel/json
  path: "output/"
  filename_template: "{date}_{category}_report.{format}"
```

### 2. 广度优先搜索模块 (src/bfs_researcher.py)

```python
#!/usr/bin/env python3
"""
广度优先搜索研究模块
基于公众号线索，进行网络深度搜索和交叉验证
"""

import asyncio
import json
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field
from urllib.parse import quote_plus
import httpx
from bs4 import BeautifulSoup
from loguru import logger


@dataclass
class ResearchItem:
    """研究条目"""
    title: str
    url: str
    source: str  # 来源：公众号/网站/搜索引擎
    source_type: str  # wechat/website/search_engine
    category: str  # 领域分类
    keywords: List[str] = field(default_factory=list)
    summary: str = ""
    verified: bool = False
    verification_sources: List[str] = field(default_factory=list)
    publish_time: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "source_type": self.source_type,
            "category": self.category,
            "keywords": self.keywords,
            "summary": self.summary,
            "verified": self.verified,
            "verification_count": len(self.verification_sources),
            "verification_sources": "; ".join(self.verification_sources[:3]),  # 最多3个
            "publish_time": self.publish_time,
        }


class BFSResearcher:
    """广度优先搜索研究器"""
    
    def __init__(self, max_depth: int = 2, max_results_per_keyword: int = 10):
        self.max_depth = max_depth
        self.max_results = max_results_per_keyword
        self.visited_urls: Set[str] = set()
        self.http = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
        )
    
    async def research(
        self, 
        seed_items: List[ResearchItem],
        categories: Dict[str, List[str]]
    ) -> List[ResearchItem]:
        """基于种子条目进行广度优先搜索
        
        Args:
            seed_items: 种子条目（来自公众号/网站）
            categories: 领域分类配置
            
        Returns:
            扩展后的研究条目列表
        """
        all_items = list(seed_items)
        current_level = list(seed_items)
        
        for depth in range(self.max_depth):
            logger.info(f"BFS深度 {depth + 1}/{self.max_depth}")
            next_level = []
            
            for item in current_level:
                # 基于当前条目搜索相关内容
                new_items = await self._expand_item(item, categories)
                
                # 去重
                for new_item in new_items:
                    if new_item.url not in self.visited_urls:
                        self.visited_urls.add(new_item.url)
                        next_level.append(new_item)
                        all_items.append(new_item)
            
            current_level = next_level[:20]  # 限制每层扩展数量
            logger.info(f"深度 {depth + 1}: 发现 {len(next_level)} 个新条目")
        
        return all_items
    
    async def _expand_item(
        self, 
        item: ResearchItem, 
        categories: Dict[str, List[str]]
    ) -> List[ResearchItem]:
        """扩展单个条目"""
        new_items = []
        
        # 提取关键词
        keywords = item.keywords or self._extract_keywords(item.title)
        
        # 用关键词搜索
        for keyword in keywords[:3]:  # 最多用3个关键词
            # 必应搜索
            bing_results = await self._search_bing(keyword, item.category)
            new_items.extend(bing_results)
            
            # 百度搜素
            baidu_results = await self._search_baidu(keyword, item.category)
            new_items.extend(baidu_results)
        
        return new_items
    
    def _extract_keywords(self, title: str) -> List[str]:
        """从标题提取关键词（简单实现）"""
        # 可以接入jieba分词或AI提取
        words = title.split()
        return [w for w in words if len(w) >= 2][:5]
    
    async def _search_bing(self, keyword: str, category: str) -> List[ResearchItem]:
        """必应搜索"""
        try:
            url = f"https://www.bing.com/search?q={quote_plus(keyword)}"
            response = await self.http.get(url)
            soup = BeautifulSoup(response.text, 'lxml')
            
            items = []
            for result in soup.select('li.b_algo')[:5]:  # 前5个结果
                title_el = result.select_one('h2 a')
                if not title_el:
                    continue
                
                items.append(ResearchItem(
                    title=title_el.get_text(strip=True),
                    url=title_el.get('href', ''),
                    source="Bing",
                    source_type="search_engine",
                    category=category,
                    keywords=[keyword]
                ))
            
            return items
            
        except Exception as e:
            logger.error(f"必应搜索失败: {e}")
            return []
    
    async def _search_baidu(self, keyword: str, category: str) -> List[ResearchItem]:
        """百度搜索"""
        try:
            url = f"https://www.baidu.com/s?wd={quote_plus(keyword)}"
            response = await self.http.get(url)
            soup = BeautifulSoup(response.text, 'lxml')
            
            items = []
            for result in soup.select('div.result, div.c-container')[:5]:
                title_el = result.select_one('h3 a')
                if not title_el:
                    continue
                
                items.append(ResearchItem(
                    title=title_el.get_text(strip=True),
                    url=title_el.get('href', ''),
                    source="百度",
                    source_type="search_engine",
                    category=category,
                    keywords=[keyword]
                ))
            
            return items
            
        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            return []
```

### 3. 交叉验证模块 (src/verifier.py)

```python
#!/usr/bin/env python3
"""
交叉验证模块
用AI验证信息的真实性和来源可靠性
"""

import asyncio
from typing import Dict, List, Optional
from loguru import logger

from .summarizer import KimiSummarizer
from .bfs_researcher import ResearchItem


class CrossVerifier:
    """交叉验证器"""
    
    VERIFICATION_PROMPT = """请验证以下科研信息的可信度，并找出相关来源：

标题: {title}
来源: {source}
分类: {category}

请执行以下任务：
1. 判断该信息是否来自可信的科研来源（学术期刊、知名机构、权威媒体）
2. 搜索并列出2-3个独立的验证来源（不同机构/媒体）
3. 给出可信度评分（1-10）

输出JSON格式:
{{
    "is_credible": true/false,
    "credibility_score": 7,
    "verification_sources": ["来源1", "来源2", "来源3"],
    "reasoning": "判断理由...",
    "suggested_category": "准确的领域分类"
}}"""

    def __init__(self, summarizer: KimiSummarizer):
        self.summarizer = summarizer
    
    async def verify_item(self, item: ResearchItem) -> ResearchItem:
        """验证单个条目"""
        if not self.summarizer.api_key:
            logger.warning("未配置Kimi API，跳过验证")
            return item
        
        try:
            prompt = self.VERIFICATION_PROMPT.format(
                title=item.title,
                source=item.source,
                category=item.category
            )
            
            response = await self.summarizer._call_api(prompt)
            
            if response:
                result = self.summarizer._parse_json(response)
                
                if result:
                    item.verified = result.get('is_credible', False)
                    item.verification_sources = result.get('verification_sources', [])
                    
                    # 更新分类建议
                    suggested = result.get('suggested_category')
                    if suggested:
                        item.category = suggested
                    
                    logger.info(f"验证完成: {item.title[:30]}... 可信度={result.get('credibility_score', 'N/A')}")
        
        except Exception as e:
            logger.error(f"验证失败: {e}")
        
        return item
    
    async def verify_batch(self, items: List[ResearchItem]) -> List[ResearchItem]:
        """批量验证"""
        tasks = [self.verify_item(item) for item in items]
        return await asyncio.gather(*tasks)
```

### 4. Excel/CSV输出模块 (src/exporter.py)

```python
#!/usr/bin/env python3
"""
数据导出模块
导出为Excel/CSV格式
"""

import csv
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime

from loguru import logger

# 尝试导入openpyxl
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


class DataExporter:
    """数据导出器"""
    
    # CSV字段定义
    CSV_FIELDS = [
        ("title", "标题"),
        ("source", "来源"),
        ("source_type", "来源类型"),
        ("category", "领域分类"),
        ("keywords", "关键词"),
        ("summary", "AI摘要"),
        ("verified", "已验证"),
        ("verification_count", "验证来源数"),
        ("verification_sources", "验证来源"),
        ("url", "链接"),
        ("publish_time", "发布时间"),
    ]
    
    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_csv(self, items: List[Dict], filename: str = None) -> str:
        """导出为CSV"""
        if not filename:
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"research_report_{date_str}.csv"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=[key for key, _ in self.CSV_FIELDS])
            writer.writeheader()
            
            # 写入中文表头
            writer.writerow({key: label for key, label in self.CSV_FIELDS})
            
            for item in items:
                row = {key: item.get(key, '') for key, _ in self.CSV_FIELDS}
                writer.writerow(row)
        
        logger.info(f"CSV已导出: {filepath}")
        return str(filepath)
    
    def export_excel(self, items: List[Dict], filename: str = None) -> str:
        """导出为Excel"""
        if not EXCEL_AVAILABLE:
            logger.warning("openpyxl未安装，降级为CSV导出")
            return self.export_csv(items, filename.replace('.xlsx', '.csv') if filename else None)
        
        if not filename:
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"research_report_{date_str}.xlsx"
        
        filepath = self.output_dir / filename
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "科研情报"
        
        # 写入表头
        for col, (_, label) in enumerate(self.CSV_FIELDS, 1):
            cell = ws.cell(row=1, column=col, value=label)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
            cell.font = Font(bold=True, color="FFFFFF")
        
        # 写入数据
        for row, item in enumerate(items, 2):
            for col, (key, _) in enumerate(self.CSV_FIELDS, 1):
                value = item.get(key, '')
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)
                ws.cell(row=row, column=col, value=value)
        
        # 调整列宽
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column].width = adjusted_width
        
        wb.save(filepath)
        logger.info(f"Excel已导出: {filepath}")
        return str(filepath)
    
    def export_by_category(self, items: List[Dict], format: str = "csv") -> Dict[str, str]:
        """按领域分类导出"""
        by_category = {}
        
        for item in items:
            cat = item.get('category', '未分类')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)
        
        exported = {}
        for cat, cat_items in by_category.items():
            safe_cat = cat.replace('/', '_').replace('\\', '_')
            date_str = datetime.now().strftime("%Y%m%d")
            filename = f"{date_str}_{safe_cat}_report.{format}"
            
            if format == 'excel':
                exported[cat] = self.export_excel(cat_items, filename)
            else:
                exported[cat] = self.export_csv(cat_items, filename)
        
        return exported
```

### 5. 主程序更新 (src/main_v2.py)

```python
#!/usr/bin/env python3
"""
科研情报监控系统 v2.0
主程序入口
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
from src.extractor import ArticleExtractor
from src.summarizer import KimiSummarizer
from src.bfs_researcher import BFSResearcher, ResearchItem
from src.verifier import CrossVerifier
from src.exporter import DataExporter
from src.storage import Database


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
    summarizer = KimiSummarizer(
        api_key=config['summarizer'].get('api_key'),
        model=config['summarizer'].get('model', 'kimi-k3'),
        api_base=config['summarizer'].get('api_base', 'https://api.moonshot.cn/v1')
    )
    bfs = BFSResearcher(
        max_depth=config['research'].get('max_depth', 2),
        max_results_per_keyword=config['research'].get('max_results', 10)
    )
    verifier = CrossVerifier(summarizer)
    exporter = DataExporter(config['output'].get('path', 'output'))
    
    all_items = []
    
    try:
        await crawler.start()
        
        # 1. 采集公众号线索
        logger.info("\n【阶段1】采集公众号线索")
        for account in config.get('wechat_accounts', []):
            if not account.get('enabled', True):
                continue
            
            logger.info(f"采集: {account['name']}")
            articles = await crawler.search_articles(account['name'], max_articles=5)
            
            for article in articles:
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
                all_items.append(item)
        
        # 2. 采集网站信息
        logger.info("\n【阶段2】采集网站信息")
        # TODO: 实现网站采集器
        
        # 3. 广度优先搜索扩展
        logger.info("\n【阶段3】广度优先搜索扩展")
        categories = config.get('categories', {})
        expanded_items = await bfs.research(all_items, categories)
        all_items.extend(expanded_items)
        
        # 4. 去重
        seen_urls = set()
        unique_items = []
        for item in all_items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_items.append(item)
        
        logger.info(f"去重后: {len(unique_items)} 条")
        
        # 5. AI交叉验证
        logger.info("\n【阶段4】AI交叉验证")
        if config['research'].get('verify', True):
            verified_items = await verifier.verify_batch(unique_items[:50])  # 限制验证数量
        else:
            verified_items = unique_items
        
        # 6. AI摘要生成
        logger.info("\n【阶段5】AI摘要生成")
        for item in verified_items[:20]:  # 限制摘要数量
            if not item.summary:
                summary = await summarizer.summarize({
                    'title': item.title,
                    'content_text': item.summary or item.title
                })
                if summary:
                    item.summary = summary.get('summary_short', '')
        
        # 7. 导出
        logger.info("\n【阶段6】导出结果")
        items_dict = [item.to_dict() for item in verified_items]
        output_format = config['output'].get('format', 'csv')
        
        if config['output'].get('by_category', False):
            exported = exporter.export_by_category(items_dict, output_format)
            logger.info(f"按分类导出: {len(exported)} 个文件")
        else:
            if output_format == 'excel':
                filepath = exporter.export_excel(items_dict)
            else:
                filepath = exporter.export_csv(items_dict)
            logger.info(f"导出: {filepath}")
        
        # 8. 保存到数据库
        for item in verified_items:
            db.save_article(item.to_dict())
        
        logger.info(f"\n完成: 共处理 {len(verified_items)} 条情报")
        
    finally:
        await crawler.close()
    
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='科研情报监控系统')
    parser.add_argument('--config', default='config/sources.yaml', help='配置文件路径')
    parser.add_argument('--output', choices=['csv', 'excel'], default=None, help='输出格式')
    
    args = parser.parse_args()
    
    # 加载配置
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 命令行覆盖
    if args.output:
        config['output']['format'] = args.output
    
    # 运行
    asyncio.run(run_research(config))


if __name__ == '__main__':
    main()
```

---

## 配置文件示例 (config/sources.yaml)

```yaml
# 科研情报监控系统配置

# 监控源
wechat_accounts:
  - name: "BioArt"
    keywords: ["BioArt", "生物医学", "基因治疗"]
    category: "生物医学"
    enabled: true
  - name: "aging"
    keywords: ["aging", "衰老", "抗衰老", "longevity"]
    category: "衰老研究"
    enabled: true
  - name: "生物谷"
    keywords: ["生物谷", "生物医药", "创新药"]
    category: "生物医药"
    enabled: true

websites:
  - name: "CK Biobank"
    url: "https://www.ckbiobank.org/"
    rss: null
    keywords: ["biobank", "cohort"]
    category: "生物样本库"
    enabled: true

# 研究配置
research:
  max_depth: 2              # BFS最大深度
  max_results: 10           # 每个关键词最大结果
  verify: true              # 是否交叉验证
  summarize: true           # 是否生成AI摘要

# 输出配置
output:
  format: "csv"             # csv/excel
  path: "output"
  by_category: true         # 按分类分别导出

# AI配置
summarizer:
  enabled: true
  api_key: "your-kimi-api-key"
  model: "kimi-k3"

# 爬虫配置
crawler:
  headless: true
  request_delay: 3

# 存储配置
storage:
  db_path: "data/research.db"
```

---

## 实施路线图

### Phase 1: 核心功能 (2-3天)
- [x] 需求确认
- [ ] 配置文件设计
- [ ] BFS搜索模块
- [ ] 交叉验证模块
- [ ] CSV/Excel导出
- [ ] 命令行界面

### Phase 2: 数据源扩展 (1-2天)
- [ ] 网站RSS采集器
- [ ] 通用搜索引擎适配器
- [ ] 更多公众号支持

### Phase 3: 优化 (1-2天)
- [ ] 去重优化
- [ ] 并发控制
- [ ] 错误重试
- [ ] 日志完善

---

## 下一步行动

1. **确认配置文件格式** - 是否需要调整字段？
2. **准备Kimi API Key** - 用于AI验证和摘要
3. **测试运行** - 先跑一个小规模测试
4. **部署到服务器** - 配置定时任务

这个方案是否符合你的需求？需要我调整哪些部分？