# bio-crawler — 生物医学情报采集与推送系统

> 本文档前半部分记录 2026-11-23 的原始需求讨论（当时定位是微信公众号监控，故下文围绕公众号展开）。
> 当前系统已演进为「AI agent 驱动的生物医学情报管线」：每日 6 路子 agent 广度采集 → 三层去重入库 →
> 关键词聚合表格推送飞书 + 本地 HTML 查看器。运行方式见 docs/agent_collection.md 与 wechat-crawler-pipeline skill（将更名 bio-crawler-pipeline）。

## 需求确认 (2026-11-23)

| 维度 | 确认结果 |
|------|---------|
| 监控规模 | 几个核心号 + 十几到几十个相关号 (~20-50个) |
| 更新频率 | 每天推送一次 |
| 推送方式 | 形式不限，先能看到即可 |
| AI摘要 | Kimi (kimi-k3) |
| 图片 | 长期保存，服务器本地存储 |
| 部署 | 服务器运行 |
| 界面 | 暂不需要，配置文件即可 |

## 技术栈 (已确认)

- Python 3.10 + Playwright (爬虫)
- SQLite (单机部署，简单可靠)
- Kimi API (AI摘要)
- 本地文件系统 (图片存储)
- 控制台输出 + 可选邮件推送 (通知)

## 数据源 (已验证)

- 搜狗微信搜索: ✅ 可用，有反爬但可处理
- RSSHub: ❌ 当前网络无法访问，放弃

## 项目结构

```
wechat-crawler/
├── config/
│   └── accounts.yaml          # 公众号配置
├── data/                      # 数据目录
│   ├── wechat.db              # SQLite数据库
│   └── images/                # 图片存储
├── src/
│   ├── __init__.py
│   ├── main.py                # 主程序入口
│   ├── crawler.py             # 搜狗微信爬虫
│   ├── extractor.py           # 正文提取
│   ├── summarizer.py          # Kimi摘要
│   ├── storage.py             # 数据库操作
│   └── notifier.py            # 通知推送
├── scripts/
│   └── init_db.py             # 初始化数据库
├── requirements.txt
└── README.md
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
playwright install chromium

# 配置公众号
cp config/accounts.yaml.example config/accounts.yaml
# 编辑 config/accounts.yaml

# 初始化数据库
python scripts/init_db.py

# 运行
python src/main.py
```

## 配置文件说明

### config/accounts.yaml

```yaml
# 核心公众号 (必须监控)
core_accounts:
  - name: "三联生活周刊"
    wechat_id: "lifeweek"
    enabled: true
  - name: "南方周末"
    wechat_id: "infzm"
    enabled: true

# 相关公众号 (可能关注)
related_accounts:
  - name: "虎嗅"
    wechat_id: "huxiu_com"
    enabled: true
  - name: "36氪"
    wechat_id: "wow36kr"
    enabled: true
  # ... 更多

# 采集设置
crawler:
  max_articles_per_account: 10      # 每个号最多采集最近几篇
  request_delay: 3                  # 请求间隔(秒)
  headless: true                    # 无头浏览器

# AI摘要
summarizer:
  enabled: true
  api_key: "your-kimi-api-key"
  model: "kimi-k3"
  max_content_length: 8000          # 发送给AI的最大字符数

# 通知
notifier:
  # 控制台输出 (默认)
  console:
    enabled: true
  
  # 邮件推送 (可选)
  email:
    enabled: false
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    username: "your-email@gmail.com"
    password: "your-password"
    to: ["you@example.com"]
  
  # 企业微信机器人 (可选)
  wecom:
    enabled: false
    webhook_url: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"

# 存储
storage:
  db_path: "data/wechat.db"
  image_dir: "data/images"
  keep_images: true                 # 是否下载图片
```

## 运行模式

### 1. 单次运行 (测试)

```bash
python src/main.py --once
```

输出示例:
```
[2026-11-23 10:00:00] 开始采集...
[2026-11-23 10:00:05] 三联生活周刊: 发现 3 篇新文章
[2026-11-23 10:00:08]   - 标题: xxx
[2026-11-23 10:00:12]   - 摘要: 这是一篇关于...的文章
[2026-11-23 10:00:15] 南方周末: 发现 2 篇新文章
...
[2026-11-23 10:05:00] 采集完成，共 15 篇新文章
[2026-11-23 10:05:01] 推送通知:
  📰 公众号更新播报 (15篇)
  1. [三联生活周刊] 标题...
     摘要: ...
  2. [南方周末] 标题...
     摘要: ...
```

### 2. 定时运行 (每天一次)

```bash
# 使用 cron
crontab -e
# 添加: 0 9 * * * cd /path/to/wechat-crawler && python src/main.py

# 或使用系统服务
sudo systemctl enable wechat-crawler
```

### 3. 交互式测试

```bash
python -c "from src.crawler import SogouCrawler; import asyncio; print(asyncio.run(SogouCrawler().test()))"
```

## 数据库结构

### articles 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| account_name | TEXT | 公众号名称 |
| title | TEXT | 文章标题 |
| url | TEXT | 文章URL |
| content_text | TEXT | 正文纯文本 |
| content_html | TEXT | 正文HTML |
| summary | TEXT | AI摘要 |
| images | JSON | 图片URL列表 |
| local_images | JSON | 本地图片路径 |
| publish_time | TEXT | 发布时间 |
| created_at | TEXT | 采集时间 |

## 开发进度

- [x] 需求确认
- [x] 数据源验证
- [x] 技术选型
- [ ] 项目骨架搭建
- [ ] 爬虫实现
- [ ] 正文提取
- [ ] 图片下载
- [ ] AI摘要
- [ ] 通知推送
- [ ] 定时任务
- [ ] 测试部署

## 常见问题

### Q: 搜狗反爬怎么办?

A: 已实现以下策略:
1. 随机 User-Agent
2. 请求间隔控制 (默认3秒)
3. 验证码检测和人工处理提示
4. 失败自动重试

如果频繁遇到验证码，可以:
- 增加 request_delay
- 使用代理池
- 考虑接入打码平台

### Q: 图片怎么长期保存?

A: 图片下载到 `data/images/` 目录，按公众号分文件夹存储。数据库保存本地路径，不依赖原始URL。

### Q: 如何添加新的公众号?

A: 编辑 `config/accounts.yaml`，在 `core_accounts` 或 `related_accounts` 中添加:
```yaml
- name: "公众号名称"
  wechat_id: "微信号"
  enabled: true
```

### Q: Kimi API 怎么获取?

A: 访问 https://platform.moonshot.cn/ 注册并创建 API Key。

## 合规提醒

1. 本工具仅用于个人学习和研究
2. 请遵守微信公众号版权协议
3. 控制采集频率，避免对目标网站造成压力
4. 不要大规模传播采集的内容
