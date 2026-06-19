#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_knockout.py 的单元测试:用真实场地/时间构造的 mock ESPN 数据,验证
回填正确、别名生效、幂等、TBD 跳过、只填占位、不动小组赛。纯标准库。
  运行:  python scripts/test_update_knockout.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_knockout as U

ROOT = Path(__file__).resolve().parents[1]
fail = 0
def ok(c, m):
    global fail
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fail += 1

def load(): return json.loads((ROOT / "data" / "matches.json").read_text(encoding="utf-8"))
def slot(ms, n): return next(m for m in ms if m["n"] == n)
def ev(home, away, ko, venue, state="pre"):
    return {"competitions": [{"date": ko, "venue": {"fullName": venue},
            "status": {"type": {"state": state}},
            "competitors": [{"homeAway": "home", "team": {"displayName": home}},
                            {"homeAway": "away", "team": {"displayName": away}}]}]}

matches = load()
cdict = U.build_dict(matches)
ok(cdict.get(U.canon("Mexico")) == ("墨西哥", "🇲🇽"), "国家字典:Mexico→墨西哥🇲🇽")
ok(cdict.get(U.canon("Brazil")) == ("巴西", "🇧🇷"), "国家字典:Brazil→巴西🇧🇷")

# 用真实槽的日期/球场:73=SoFi(R32),89=Lincoln Financial(R16),104=MetLife(决赛)
s73, s89, s104 = slot(matches, 73), slot(matches, 89), slot(matches, 104)
payload = {"events": [
    ev("Mexico", "Brazil", s73["ko"].replace("Z", "Z"), s73["v"]),
    ev("South Korea", "USA", s89["ko"], s89["v"]),          # 别名:South Korea→韩国, USA→美国
    ev("Argentina", "France", s104["ko"], s104["v"]),
    ev("TBD", "TBD", s104["ko"], "Somewhere"),               # 应被跳过
]}
events = U.parse_events(payload)
log = []
changes = U.apply_updates(matches, events, cdict, log)

print("测试 1 · 回填正确:")
ok(changes == 3, "回填 3 场(TBD 那条被跳过),实际 %d" % changes)
m73 = slot(matches, 73)
ok((m73["h"], m73["hz"], m73["hf"]) == ("Mexico", "墨西哥", "🇲🇽"), "第73场主队=🇲🇽墨西哥")
ok((m73["a"], m73["az"], m73["af"]) == ("Brazil", "巴西", "🇧🇷"), "第73场客队=🇧🇷巴西")
m89 = slot(matches, 89)
ok((m89["hz"], m89["hf"]) == ("韩国", "🇰🇷"), "第89场主队别名 South Korea→🇰🇷韩国")
ok((m89["az"], m89["af"]) == ("美国", "🇺🇸"), "第89场客队别名 USA→🇺🇸美国")
m104 = slot(matches, 104)
ok((m104["hz"], m104["az"]) == ("阿根廷", "法国"), "决赛=阿根廷 vs 法国")

print("测试 2 · 幂等(再跑一次不应再改):")
log2 = []
changes2 = U.apply_updates(matches, events, cdict, log2)
ok(changes2 == 0, "第二次回填 0 场,实际 %d" % changes2)

print("测试 3 · 只填占位、不动小组赛、总数不变:")
ok(len(matches) == 104, "仍 104 场")
g = slot(matches, 1)
ok((g["hz"], g["hf"]) == ("墨西哥", "🇲🇽"), "小组赛第1场未被改动")
# 未被 mock 覆盖的淘汰赛槽仍是占位
m74 = slot(matches, 74)
ok(not (m74["hf"] and m74["af"]), "未覆盖的第74场仍是占位(无国旗)")

print("测试 4 · TBD / 未识别队名跳过:")
fresh = load()
cd = U.build_dict(fresh)
bad = U.parse_events({"events": [ev("Atlantis", "Wakanda", slot(fresh,73)["ko"], slot(fresh,73)["v"])]})
lg = []
ok(U.apply_updates(fresh, bad, cd, lg) == 0, "未知国家不回填")

if fail:
    print("\n❌ %d 个断言失败" % fail); sys.exit(1)
print("\n✅ 全部通过")
