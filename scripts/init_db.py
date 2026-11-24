#!/usr/bin/env python3
"""
初始化数据库
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.storage import Database


def main():
    """初始化数据库"""
    db_path = project_root / "data" / "wechat.db"

    # 确保数据目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"初始化数据库: {db_path}")

    db = Database(str(db_path))
    db.init_db()

    print("数据库初始化完成")
    print(f"数据库文件: {db_path}")
    print(f"图片目录: {project_root / 'data' / 'images'}")


if __name__ == "__main__":
    main()
