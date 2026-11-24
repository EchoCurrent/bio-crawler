#!/usr/bin/env python3
"""
采集结果聚合脚本

合并 data/collection/<date>/ 下所有子 agent 产出的 JSONL:
  1. 校验必填字段与 URL 格式, 丢弃坏行
  2. 去重: URL 归一化 + 标题归一化 双重判定 (跨子 agent 重复会合并)
  3. 跳过 research.db 中已存在的 URL
  4. 新条目写入 research.db, 全量去重结果导出 merged.jsonl + CSV

用法:
  python scripts/aggregate_collection.py                 # 聚合今天日期的目录
  python scripts/aggregate_collection.py --date 20261123
  python scripts/aggregate_collection.py --dir data/collection/20261123
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import Database  # noqa: E402

REQUIRED_FIELDS = ["title", "url", "source", "summary"]
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                   "fbclid", "gclid", "spm", "ref", "ref_src"}


def normalize_url(url: str) -> str:
    """URL 归一化: 去 tracking 参数、host 小写、去末尾斜杠"""
    try:
        p = urlparse(url.strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            return ""
        query = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "",
                           urlencode(query), ""))
    except Exception:
        return ""


def normalize_title(title: str) -> str:
    """标题归一化: 小写、去标点空白、截断 20 字"""
    t = re.sub(r"[\s\W_]+", "", title.lower())
    return t[:20]


def valid_item(item: dict) -> bool:
    if not isinstance(item, dict):
        return False
    for f in REQUIRED_FIELDS:
        v = item.get(f)
        if not v or not str(v).strip():
            return False
    if not normalize_url(str(item.get("url", ""))):
        return False
    return True


def aggregate(wave_dir: Path, db: Database) -> dict:
    stats = {"files": 0, "lines": 0, "bad": 0, "dup_within_wave": 0,
             "already_in_db": 0, "new": 0}
    by_url: dict[str, dict] = {}
    by_title: dict[str, str] = {}  # normalized_title -> canonical_url

    for fp in sorted(wave_dir.glob("*.jsonl")):
        if fp.name.startswith("merged"):
            continue
        stats["files"] += 1
        for line in fp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            stats["lines"] += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                stats["bad"] += 1
                continue
            if not valid_item(item):
                stats["bad"] += 1
                continue

            nurl = normalize_url(item["url"])
            ntitle = normalize_title(item["title"])

            # 标题撞车且 URL 不同 -> 视为同一事件的不同来源, 合并到已有条目
            if ntitle in by_title and by_title[ntitle] != nurl:
                existing = by_url.get(by_title[ntitle])
                if existing is not None:
                    existing.setdefault("alt_sources", [])
                    alt = {"url": item["url"], "source": item.get("source", "")}
                    if alt not in existing["alt_sources"]:
                        existing["alt_sources"].append(alt)
                    stats["dup_within_wave"] += 1
                    continue

            if nurl in by_url:
                stats["dup_within_wave"] += 1
                continue

            item["_nurl"] = nurl
            by_url[nurl] = item
            if ntitle:
                by_title[ntitle] = nurl

    # 与库中历史数据去重
    fresh = []
    for nurl, item in by_url.items():
        if db.article_exists(nurl):
            stats["already_in_db"] += 1
        else:
            fresh.append(item)

    # 写库
    for item in fresh:
        db.save_article({
            "account_name": item.get("source", ""),
            "title": item["title"],
            "url": item["_nurl"],
            "publish_time": item.get("published_time", ""),
            "digest": item.get("summary", ""),
            "summary": item.get("summary", ""),
            "category": item.get("category", "生物医学"),
            "tags": [item.get("subtopic", ""), f"relevance:{item.get('relevance', 'medium')}"]
                      + ([json.dumps(item["alt_sources"], ensure_ascii=False)]
                         if item.get("alt_sources") else []),
            "model_used": "agent-collection",
        })
        stats["new"] += 1

    # 导出 merged.jsonl (本轮全部去重后条目, 含历史已存在标记)
    merged_path = wave_dir / "merged.jsonl"
    with open(merged_path, "w", encoding="utf-8") as f:
        for nurl, item in sorted(by_url.items(), key=lambda kv: kv[1].get("title", "")):
            item = dict(item)
            item.pop("_nurl", None)
            item["in_db_before_wave"] = nurl not in {i["_nurl"] for i in fresh}
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 导出 CSV
    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    date_tag = wave_dir.name
    csv_path = out_dir / f"{date_tag}_生物医学_report.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["标题", "来源", "类型", "子方向", "摘要", "相关度", "发布时间", "链接", "交叉来源"])
        for nurl, item in sorted(by_url.items(), key=lambda kv: kv[1].get("title", "")):
            alts = item.get("alt_sources", [])
            w.writerow([
                item["title"], item.get("source", ""), item.get("source_type", ""),
                item.get("subtopic", ""), item.get("summary", ""),
                item.get("relevance", ""), item.get("published_time", ""),
                nurl,
                "; ".join(f"{a['source']}: {a['url']}" for a in alts),
            ])

    return {"stats": stats, "merged": str(merged_path), "csv": str(csv_path),
            "total_unique": len(by_url)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    p.add_argument("--dir", default=None)
    p.add_argument("--db", default=None, help="测试时指定其他数据库路径")
    args = p.parse_args()

    wave_dir = Path(args.dir) if args.dir else PROJECT_ROOT / "data" / "collection" / args.date
    if not wave_dir.is_dir():
        sys.exit(f"采集目录不存在: {wave_dir}")

    db = Database(args.db or str(PROJECT_ROOT / "data" / "research.db"))
    db.init_db()

    result = aggregate(wave_dir, db)
    s = result["stats"]
    print(f"输入文件: {s['files']} 个, 原始行: {s['lines']}")
    print(f"坏行丢弃: {s['bad']}")
    print(f"轮内重复合并: {s['dup_within_wave']}")
    print(f"库中已存在(跳过): {s['already_in_db']}")
    print(f"新入库: {s['new']}")
    print(f"本轮唯一条目: {result['total_unique']}")
    print(f"merged: {result['merged']}")
    print(f"csv: {result['csv']}")


if __name__ == "__main__":
    main()
