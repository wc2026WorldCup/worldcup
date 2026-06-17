#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键构建:网页 (index.html) + 日历 (worldcup.ics)。

用法:
    python scripts/build_all.py

产物输出到项目根目录,可直接上传到 GitHub Pages。
"""
import sys
from pathlib import Path

# 确保无论从哪个目录运行,都能 import 同级的两个构建脚本
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_site
import build_calendar

if __name__ == "__main__":
    build_site.build()
    build_calendar.build()
    print("✅ 全部完成：index.html 与 worldcup.ics 已生成在项目根目录,可直接上传到 GitHub 仓库。")
