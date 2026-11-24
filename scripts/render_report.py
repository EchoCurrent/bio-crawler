#!/usr/bin/env python3
"""
日报渲染推送: 读取 themes.json (主题聚类结果) + merged.jsonl (条目池),
渲染飞书交互式卡片并推送。

用法:
  python scripts/render_report.py --themes data/collection/20261123/themes.json

themes.json 格式见 data/collection/20261123/themes.json 示例;
item_indexes 指向 merged.jsonl 的 0 起始行号。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.feishu_notifier import FeishuAppNotifier  # noqa: E402


def load_config():
    from src.config_loader import load_config
    return load_config()


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--themes", required=True)
    p.add_argument("--max-items-per-section", type=int, default=5)
    args = p.parse_args()

    themes_path = Path(args.themes)
    wave_dir = themes_path.parent
    merged = [json.loads(l) for l in (wave_dir / "merged.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    themes = json.loads(themes_path.read_text(encoding="utf-8"))

    n_high = sum(1 for it in merged if it.get("relevance") == "high")
    elements = [
        {"tag": "div", "text": {"tag": "lark_md",
         "content": f"**{themes.get('note', '')}**\n\n相关度 high: {n_high} 条"}},
        {"tag": "hr"},
    ]

    for sec in themes["sections"]:
        idxs = sec.get("item_indexes", [])[: args.max_items_per_section]
        if not idxs:
            continue
        elements.append({"tag": "div", "text": {"tag": "lark_md",
                        "content": f"**【{sec['name']}】**"}})
        if sec.get("theme"):
            elements.append({"tag": "div", "text": {"tag": "lark_md",
                            "content": f"_{sec['theme']}_"}})
        for i in idxs:
            if i >= len(merged):
                continue
            it = merged[i]
            title = it["title"][:48]
            src = it.get("source", "")
            summary = it.get("summary", "")[:36]
            line = f"▸ **{title}**\n  📍 {src}  {summary}"
            if it.get("url"):
                line += f"\n  🔗 [查看原文]({it['url']})"
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": line}})

    cfg = load_config()["feishu"]["app"]
    notifier = FeishuAppNotifier(cfg["app_id"], cfg["app_secret"], cfg["chat_id"])
    ok = await notifier.send_interactive_card(themes.get("title", "科研情报日报"), elements)
    await notifier.close()
    print(f"card elements: {len(elements)}")
    if not ok:
        sys.exit("发送失败")


if __name__ == "__main__":
    asyncio.run(main())
