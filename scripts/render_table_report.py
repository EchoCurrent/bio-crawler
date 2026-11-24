#!/usr/bin/env python3
"""
关键词聚合表格日报: 读取 merged.jsonl, 按关键词分组合并,
渲染为飞书表格卡片推送 (每主题一张表: 标题带原文链接 | 来源 | 一句话摘要)。

用法:
  python scripts/render_table_report.py --date 20261123
  python scripts/render_table_report.py --merged data/collection/20261123/merged.jsonl
"""

import argparse
import asyncio
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.feishu_notifier import FeishuAppNotifier  # noqa: E402

# 关键词规则: 顺序即优先级, 标题+摘要命中首个模式即归入该类
KEYWORD_RULES = OrderedDict([
    ("CAR-T/细胞治疗", [r"car[- ]?t", r"ucar", r"体内car", r"carvivo", r"嵌合抗原受体",
                        r"gpc3", r"cldn18\.2", r"通用型.*细胞", r"细胞疗法"]),
    ("基因编辑", [r"crispr", r"casgevy", r"碱基编辑", r"先导编辑", r"prime editing",
                  r"verve", r"脱靶", r"apoc3", r"pcsk9", r"基因编辑"]),
    ("基因治疗", [r"aav", r"基因疗法", r"基因治疗", r"elevidys", r"waskyra", r"itvisma",
                  r"sma", r"血友病", r"信玖凝", r"体内基因"]),
    ("干细胞/再生医学", [r"干细胞", r"ipsc", r"胰岛细胞", r"zimislecel", r"重编程", r"类器官", r"艾米迈托"]),
    ("ADC", [r"adc", r"抗体偶联", r"trop2", r"her2", r"egfr×her3"]),
    ("双抗/多抗", [r"双抗", r"双特异性", r"dll3", r"依沃西", r"塔拉妥", r"玛仕度肽之外的.*抗体",
                   r"三抗"]),
    ("GLP-1/代谢", [r"glp-1", r"替尔泊肽", r"司美格鲁肽", r"玛仕度肽", r"orforglipron", r"减重", r"降糖"]),
    ("PROTAC", [r"protac", r"降解剂", r"vepdegestrant", r"arv-471"]),
    ("AI制药", [r"ai制药", r"ai药物", r"英矽", r"生成式ai", r"ai加速新药", r"ai4s"]),
    ("早筛/液体活检", [r"galleri", r"mced", r"多癌种", r"液体活检", r"cfdna", r"ctdna",
                        r"甲基化.*早筛", r"shield", r"早筛", r"常卫清", r"世和基因"]),
    ("伴随诊断", [r"伴随诊断", r"cdx", r"试剂盒.*获批", r"艾惠捷"]),
    ("抗衰老药物", [r"雷帕霉素", r"rapamycin", r"西罗莫司", r"senolytic", r"达沙替尼", r"槲皮素",
                    r"ubx1325", r"tame", r"二甲双胍", r"nmn", r"nad\+?", r"衰老细胞.*清除", r"抗衰老药"]),
    ("衰老机制/长寿", [r"sirt", r"表观.*时钟", r"甲基化时钟", r"长寿", r"百岁", r"衰老机制",
                       r"细胞衰老", r"端粒", r"衰老.*综述"]),
    ("队列/生物样本库", [r"biobank", r"队列", r"cohort", r"uk biobank", r"\bukb\b", r"ckb",
                          r"all of us", r"finngen", r"华西百万", r"泰州队列", r"开滦", r"sg100k",
                          r"样本库", r"人遗", r"百万人群", r"naKo".lower()]),
    ("医保/支付", [r"医保", r"商保", r"基药目录", r"双目录", r"支付", r"集采"]),
    ("出海/BD交易", [r"license", r"\bbd\b", r"授权.*亿美元", r"出海", r"亿美元", r"newco",
                      r"\bgsk\b", r"勃林格", r"summit"]),
    ("监管/审批政策", [r"nmpa", r"\bfda\b", r"获批", r"批准", r"审评", r"突破性疗法",
                       r"优先审评", r"号令", r"办法", r"细则", r"临床默示许可", r"ind"]),
    ("临床试验动态", [r"临床试验", r"i{1,3}v?期", r"iii期", r"ii期", r"i期", r"失败",
                       r"主要终点", r"RCT"]),
    ("投融资/产业", [r"融资", r"园区", r"cxo", r"cro", r"中报", r"排行榜", r"投资", r"财报"]),
])

FALLBACK = "其它"


def classify(item: dict) -> str:
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    for kw, patterns in KEYWORD_RULES.items():
        if any(re.search(p, text) for p in patterns):
            return kw
    return FALLBACK


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None)
    p.add_argument("--merged", default=None)
    p.add_argument("--max-per-kw", type=int, default=12)
    p.add_argument("--title", default=None)
    args = p.parse_args()

    merged_path = Path(args.merged) if args.merged else \
        PROJECT_ROOT / "data" / "collection" / (args.date or "20261123") / "merged.jsonl"
    items = [json.loads(l) for l in merged_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    groups: "OrderedDict[str, list]" = OrderedDict((kw, []) for kw in KEYWORD_RULES)
    groups[FALLBACK] = []
    for it in items:
        groups.setdefault(classify(it), []).append(it)
    for g in groups.values():
        g.sort(key=lambda x: (x.get("relevance") != "high", x.get("title", "")))

    n_high = sum(1 for it in items if it.get("relevance") == "high")
    elements = [{"tag": "div", "text": {"tag": "lark_md",
                 "content": f"**共 {len(items)} 条 | 关键词聚合 | high {n_high} 条**\n_完整数据见 CSV / research.db_"}}]

    # 单张大表: 关键词列做分组, 行数控制在 --max-per-kw 内
    rows = []
    for kw, g in groups.items():
        if not g:
            continue
        for it in g[: args.max_per_kw]:
            title = it["title"][:40].replace("|", "/").replace("\n", " ")
            url = it.get("url", "")
            cell = {"type": "lark_md", "content": f"[{title}]({url})"} if url else title
            rows.append({
                "kw": kw if it is g[0] else "",
                "title": cell,
                "src": (it.get("source", "") or "-")[:16],
                "sum": (it.get("summary", "") or "-").replace("|", "/")[:30],
            })
    elements.append({
        "tag": "table",
        "columns": [
            {"name": "kw", "display_name": "关键词", "data_type": "text", "width": "130px"},
            {"name": "title", "display_name": "标题(链接)", "data_type": "text", "width": "auto"},
            {"name": "src", "display_name": "来源", "data_type": "text", "width": "120px"},
            {"name": "sum", "display_name": "摘要", "data_type": "text", "width": "auto"},
        ],
        "rows": rows,
        "header_style": {"background_style": "grey", "text_align": "center",
                         "bold": True, "text_size": "normal"},
    })

    from src.config_loader import load_config
    cfg = load_config()["feishu"]["app"]
    notifier = FeishuAppNotifier(cfg["app_id"], cfg["app_secret"], cfg["chat_id"])
    title = args.title or f"🧬 生物医学情报日报 · {merged_path.parent.name} · 关键词聚合表"
    ok = await notifier.send_interactive_card(title, elements)
    msg_id = notifier.last_message_id
    await notifier.close()
    print(f"elements={len(elements)}, table_rows={len(rows)}, message_id={msg_id}")
    if not ok:
        sys.exit("发送失败")


if __name__ == "__main__":
    asyncio.run(main())
