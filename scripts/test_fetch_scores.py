#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_scores.py 单测:验证 ESPN→场次号映射、主客方向归一、别名、winner 标志(点球),
以及只取 in/post 状态。纯标准库。
  运行:  python scripts/test_fetch_scores.py
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_scores as F

ROOT = Path(__file__).resolve().parents[1]
fail = 0
def ok(c, m):
    global fail
    print(("  ✓ " if c else "  ✗ ") + m)
    if not c: fail += 1

matches = json.loads((ROOT / "data" / "matches.json").read_text(encoding="utf-8"))
idx = F.pair_index(matches)
def slot(n): return next(m for m in matches if m["n"] == n)
def ev(home, away, hs, as_, state="post", wH=False, wA=False):
    return {"competitions": [{"status": {"type": {"state": state}},
        "competitors": [{"homeAway": "home", "team": {"displayName": home}, "score": str(hs), "winner": wH},
                        {"homeAway": "away", "team": {"displayName": away}, "score": str(as_), "winner": wA}]}]}

s1, s2, s4 = slot(1), slot(2), slot(4)   # 墨西哥-南非 / 韩国-捷克 / 美国-巴拉圭
payload = {"events": [
    ev(s1["h"], s1["a"], 3, 1),                  # 正向
    ev(s2["a"], s2["h"], 2, 0),                  # ESPN 主客与我们相反 → 应归一
    ev("USA", "Paraguay", 1, 1, wH=True),        # 别名(USA→美国)+ 点球(1:1 靠 winner)
]}
sc = F.parse_scores([payload], idx)

print("测试 1 · 比分映射与方向归一:")
ok(sc.get(1) == {"hs": 3, "as": 1, "live": False, "w": None}, "第1场 3:1 正向")
ok(sc.get(2) and sc[2]["hs"] == 0 and sc[2]["as"] == 2, "第2场 ESPN 反向 → 归一为 主0:客2")

print("测试 2 · 别名 + 点球 winner:")
ok(sc.get(4) and sc[4]["hs"] == 1 and sc[4]["as"] == 1, "第4场(USA→美国)比分 1:1")
ok(sc.get(4) and sc[4]["w"] == "h", "1:1 但 winner=主 → w='h'(点球判得准)")

print("测试 3 · 只取 in/post:")
sc2 = F.parse_scores([{"events": [ev(s1["h"], s1["a"], 0, 0, state="pre")]}], idx)
ok(1 not in sc2, "未开赛(pre)不计入")

print("测试 4 · 进行中标记:")
sc3 = F.parse_scores([{"events": [ev(s1["h"], s1["a"], 1, 0, state="in")]}], idx)
ok(sc3.get(1) and sc3[1]["live"] is True, "进行中(in)标 live=True")

print("测试 5 · 按场地+日期回填未确定的淘汰赛(带队伍):")
import update_knockout as U2
nat = U2.build_dict(matches)
kf = {"n": 901, "sk": "round-of-32", "st": "32强赛", "g": None,
      "h": "Group A runners-up", "a": "Group B runners-up",
      "hz": "A组第2", "az": "B组第2", "hf": "", "af": "", "c": "X", "v": "Test Venue Z", "ko": "2026-07-15T19:00:00Z"}
kovd = {U2.our_ko(kf).strftime("%Y%m%d") + "|" + U2.norm(kf["v"]): kf}
evVD = {"competitions": [{"date": "2026-07-15T19:00:00Z", "venue": {"fullName": "Test Venue Z"},
        "status": {"type": {"state": "post"}},
        "competitors": [{"homeAway": "home", "team": {"displayName": "Argentina"}, "score": "2", "winner": True},
                        {"homeAway": "away", "team": {"displayName": "Germany"}, "score": "1", "winner": False}]}]}
sv = F.parse_scores([{"events": [evVD]}], {}, kovd, nat)   # idx 为空 → 走场地+日期分支
ok(sv.get(901) is not None, "按场地+日期命中淘汰赛槽 901")
ok(sv.get(901) and (sv[901]["hz"], sv[901]["az"]) == ("阿根廷", "德国"), "回填真实队名 阿根廷/德国")
ok(sv.get(901) and (sv[901]["hf"], sv[901]["af"]) == ("🇦🇷", "🇩🇪"), "带国旗")
ok(sv.get(901) and sv[901]["hs"] == 2 and sv[901]["as"] == 1 and sv[901]["w"] == "h", "比分与胜者(以 ESPN 主为主)")

if fail: print("\n❌ %d 个断言失败" % fail); sys.exit(1)
print("\n✅ 全部通过")
