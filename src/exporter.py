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
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    logger.warning("openpyxl未安装，Excel导出功能不可用")


class DataExporter:
    """数据导出器"""

    # 字段定义 (key, 中文标签, 列宽)
    FIELDS = [
        ("title", "标题", 50),
        ("source", "来源", 15),
        ("source_type", "来源类型", 12),
        ("category", "领域分类", 15),
        ("keywords", "关键词", 30),
        ("summary", "AI摘要", 60),
        ("verified", "已验证", 8),
        ("credibility_score", "可信度", 8),
        ("verification_count", "验证来源数", 10),
        ("verification_sources", "验证来源", 40),
        ("url", "链接", 50),
        ("publish_time", "发布时间", 15),
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
            writer = csv.writer(f)

            # 写入表头
            headers = [label for _, label, _ in self.FIELDS]
            writer.writerow(headers)

            # 写入数据
            for item in items:
                row = []
                for key, _, _ in self.FIELDS:
                    value = item.get(key, '')
                    if isinstance(value, list):
                        value = ', '.join(str(v) for v in value)
                    row.append(value)
                writer.writerow(row)

        logger.info(f"CSV已导出: {filepath} ({len(items)} 条)")
        return str(filepath)

    def export_excel(self, items: List[Dict], filename: str = None) -> str:
        """导出为Excel"""
        if not EXCEL_AVAILABLE:
            logger.warning("openpyxl未安装，降级为CSV导出")
            csv_filename = filename.replace('.xlsx', '.csv') if filename else None
            return self.export_csv(items, csv_filename)

        if not filename:
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"research_report_{date_str}.xlsx"

        filepath = self.output_dir / filename

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "科研情报"

        # 样式定义
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")

        thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # 写入表头
        for col, (_, label, width) in enumerate(self.FIELDS, 1):
            cell = ws.cell(row=1, column=col, value=label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = thin_border

            # 设置列宽
            col_letter = get_column_letter(col)
            ws.column_dimensions[col_letter].width = width

        # 冻结首行
        ws.freeze_panes = 'A2'

        # 写入数据
        for row, item in enumerate(items, 2):
            for col, (key, _, _) in enumerate(self.FIELDS, 1):
                value = item.get(key, '')
                if isinstance(value, list):
                    value = ', '.join(str(v) for v in value)

                cell = ws.cell(row=row, column=col, value=value)
                cell.border = thin_border

                # 已验证的行用绿色标记
                if key == "verified" and value == "是":
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

        # 自动筛选
        ws.auto_filter.ref = ws.dimensions

        wb.save(filepath)
        logger.info(f"Excel已导出: {filepath} ({len(items)} 条)")
        return str(filepath)

    def export_by_category(
        self,
        items: List[Dict],
        format: str = "csv",
        date_str: str = None
    ) -> Dict[str, str]:
        """按领域分类导出"""
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")

        # 按分类分组
        by_category = {}
        for item in items:
            cat = item.get('category', '未分类')
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(item)

        # 导出每个分类
        exported = {}
        for cat, cat_items in by_category.items():
            safe_cat = cat.replace('/', '_').replace('\\', '_').replace(' ', '_')
            filename = f"{date_str}_{safe_cat}_report.{format}"

            if format == 'excel':
                exported[cat] = self.export_excel(cat_items, filename)
            else:
                exported[cat] = self.export_csv(cat_items, filename)

        logger.info(f"按分类导出: {len(exported)} 个文件")
        return exported

    def export_summary_stats(self, items: List[Dict], filepath: str = None) -> str:
        """导出统计摘要"""
        if not filepath:
            date_str = datetime.now().strftime("%Y%m%d_%H%M")
            filepath = self.output_dir / f"summary_stats_{date_str}.txt"

        # 统计
        total = len(items)
        verified = sum(1 for i in items if i.get('verified') == '是')
        by_source = {}
        by_category = {}

        for item in items:
            source = item.get('source', '未知')
            category = item.get('category', '未分类')

            by_source[source] = by_source.get(source, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("科研情报采集统计摘要\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"总条目数: {total}\n")
            f.write(f"已验证: {verified} ({verified/total*100:.1f}%)\n\n")

            f.write("按来源统计:\n")
            for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
                f.write(f"  {source}: {count}\n")

            f.write("\n按分类统计:\n")
            for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
                f.write(f"  {cat}: {count}\n")

        logger.info(f"统计摘要已导出: {filepath}")
        return str(filepath)
