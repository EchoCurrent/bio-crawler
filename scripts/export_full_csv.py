#!/usr/bin/env python3
"""
全量数据 CSV 导出: research.db 全部条目 -> data/intel_full.csv
带关键词分类列 (规则与飞书日报/viewer 一致), 该文件纳入 git 持续维护。

用法: venv/bin/python scripts/export_full_csv.py
"""

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from render_table_report import classify  # noqa: E402


def extract_meta(tags_json: str):
    sub, rel, alts = "", "medium", []
    try:
        tags = json.loads(tags_json or "[]")
    except json.JSONDecodeError:
        return sub, rel, alts
    for t in tags:
        if isinstance(t, str):
            if t.startswith("relevance:"):
                rel = t.split(":", 1)[1]
            elif not sub:
                sub = t
            try:
                parsed = json.loads(t)
                if isinstance(parsed, list):
                    alts = parsed
            except (json.JSONDecodeError, TypeError):
                pass
    return sub, rel, alts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(PROJECT_ROOT / "data" / "research.db"))
    p.add_argument("--out", default=str(PROJECT_ROOT / "data" / "intel_full.csv"))
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT account_name, title, url, publish_time, digest, tags, created_at "
        "FROM articles ORDER BY created_at DESC, id DESC"
    ).fetchall()
    conn.close()

    out = Path(args.out)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["关键词", "标题", "来源", "子方向", "摘要", "相关度",
                    "发布时间", "入库时间", "链接", "交叉来源"])
        for r in rows:
            sub, rel, alts = extract_meta(r["tags"])
            summary = (r["digest"] or "")[:120]
            w.writerow([
                classify({"title": r["title"], "summary": summary}),
                r["title"], r["account_name"], sub, summary, rel,
                r["publish_time"] or "", (r["created_at"] or "")[:19], r["url"],
                "; ".join(f"{a.get('source','')}: {a.get('url','')}" for a in alts),
            ])

    print(f"已导出 {len(rows)} 条 -> {out} ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
