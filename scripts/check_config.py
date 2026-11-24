#!/usr/bin/env python3
"""
配置检查工具
帮助用户检查配置是否正确
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml
from loguru import logger


def check_config(config_path: str = "config/sources.yaml"):
    """检查配置文件"""
    logger.info("=" * 60)
    logger.info("配置检查")
    logger.info("=" * 60)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    issues = []

    # 检查监控源
    logger.info("\n【监控源配置】")
    wechat_accounts = config.get('wechat_accounts', [])
    websites = config.get('websites', [])
    logger.info(f"  公众号: {len(wechat_accounts)} 个")
    logger.info(f"  网站: {len(websites)} 个")

    if not wechat_accounts and not websites:
        issues.append("未配置任何监控源")

    for acc in wechat_accounts:
        if not acc.get('keywords'):
            issues.append(f"公众号 '{acc.get('name')}' 未配置关键词")

    # 检查AI配置
    logger.info("\n【AI配置】")
    claude_config = config.get('claude', {})
    kimi_config = config.get('summarizer', {})

    if claude_config.get('enabled'):
        api_key = claude_config.get('api_key', '')
        if api_key == "your-claude-api-key-here" or not api_key:
            issues.append("Claude API Key 未配置")
        else:
            logger.info(f"  Claude: 已启用 (模型: {claude_config.get('model', 'claude-opus-5-5')})")
    elif kimi_config.get('enabled'):
        api_key = kimi_config.get('api_key', '')
        if api_key == "your-kimi-api-key-here" or not api_key:
            issues.append("Kimi API Key 未配置")
        else:
            logger.info(f"  Kimi: 已启用 (模型: {kimi_config.get('model', 'kimi-k3')})")
    else:
        issues.append("AI功能未启用 (Claude和Kimi都未启用)")
        logger.warning("  AI功能未启用")

    # 检查飞书配置
    logger.info("\n【飞书配置】")
    feishu_config = config.get('feishu', {})
    webhook = feishu_config.get('webhook', {})
    app = feishu_config.get('app', {})

    if webhook.get('enabled'):
        if webhook.get('url') == "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx":
            issues.append("飞书Webhook URL 未配置")
        else:
            logger.info("  Webhook方式: 已启用")
    elif app.get('enabled'):
        if app.get('app_id') == "cli_xxxxxx":
            issues.append("飞书应用 App ID 未配置")
        else:
            logger.info("  应用方式: 已启用")
    else:
        logger.warning("  飞书通知未启用")
        logger.info("  提示: 配置飞书后可以实现自动推送")

    # 检查输出配置
    logger.info("\n【输出配置】")
    output_config = config.get('output', {})
    logger.info(f"  格式: {output_config.get('format', 'csv')}")
    logger.info(f"  按分类: {output_config.get('by_category', False)}")

    # 检查结果
    logger.info("\n" + "=" * 60)
    if issues:
        logger.warning("发现以下问题:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        logger.info("\n请根据提示修改配置文件")
    else:
        logger.info("✓ 配置检查通过")
    logger.info("=" * 60)

    return len(issues) == 0


def print_setup_guide():
    """打印配置指南"""
    guide = """
================================================================================
快速配置指南
================================================================================

1. 配置Kimi API (用于AI验证和摘要)
   - 访问 https://platform.moonshot.cn/
   - 注册并创建 API Key
   - 修改 config/sources.yaml:
     summarizer:
       api_key: "your-actual-api-key"

2. 配置Claude API (可选，用于更高质量的分析)
   - 访问 https://console.anthropic.com/
   - 获取 API Key
   - 修改 config/sources.yaml:
     claude:
       enabled: true
       api_key: "sk-ant-..."

3. 配置飞书通知 (可选，用于每日推送)

   方式A - Webhook机器人 (简单):
   - 在飞书群聊中添加"自定义机器人"
   - 获取Webhook地址
   - 修改 config/sources.yaml:
     feishu:
       webhook:
         enabled: true
         url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx"

   方式B - 飞书应用 (功能丰富):
   - 访问 https://open.feishu.cn/
   - 创建企业自建应用
   - 获取 App ID 和 App Secret
   - 修改 config/sources.yaml:
     feishu:
       app:
         enabled: true
         app_id: "cli_xxxxx"
         app_secret: "xxxxx"
         chat_id: "oc_xxxxx"  # 群聊ID

4. 运行测试
   # 基础测试 (不启用AI和飞书)
   python src/main_v2.py --no-verify --no-summarize --max-depth 0

   # 完整测试
   python src/main_v2.py

================================================================================
"""
    print(guide)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='配置检查工具')
    parser.add_argument('--config', default='config/sources.yaml', help='配置文件路径')
    parser.add_argument('--guide', action='store_true', help='显示配置指南')

    args = parser.parse_args()

    if args.guide:
        print_setup_guide()
    else:
        check_config(args.config)
