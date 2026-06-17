#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把比赛数据 (data/matches.json) 注入网页模板 (src/template.html),
生成可直接部署的 index.html(放到 GitHub Pages 根目录即上线)。

用法:
    python scripts/build_site.py

依赖:仅 Python 标准库。
"""
import json
from pathlib import Path

ROOT     = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "src" / "template.html"
DATA     = ROOT / "data" / "matches.json"
OUT      = ROOT / "index.html"

# 网页右上角 “FIFA 官网 ↗” 按钮指向的官方赛程/赛果页(改这里即可换链接)
FIFA_URL = ("https://www.fifa.com/en/tournaments/mens/worldcup/"
            "canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums")


def build() -> str:
    template  = TEMPLATE.read_text(encoding="utf-8")
    data_text = DATA.read_text(encoding="utf-8")      # JSON 本身就是合法的 JS 字面量,原样注入
    matches   = json.loads(data_text)                  # 仅用于校验 + 计数

    html = template.replace("__DATA__", data_text).replace("__FIFA__", FIFA_URL)
    if "__DATA__" in html or "__FIFA__" in html:
        raise SystemExit("ERROR: 占位符 __DATA__ / __FIFA__ 未全部替换,请检查 src/template.html")

    OUT.write_text(html, encoding="utf-8")
    print(f"✓ index.html 生成完毕：{len(matches)} 场比赛, {len(html.encode('utf-8'))} 字节")
    return html


if __name__ == "__main__":
    build()
