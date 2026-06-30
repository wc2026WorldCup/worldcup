#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_knockout.py 的单元测试。

设计要点:回填/幂等/别名/变音/TBD 等用例使用**自造的占位淘汰赛槽(fixture)**,
不依赖 data/matches.json 的实时状态 —— 否则赛事进行中(淘汰赛已回填真实队伍)会让
"断言某槽仍是占位"之类的测试失败。国家字典从真实小组赛行构建(小组赛队名始终是真实的,稳定)。
纯标准库。  运行:  python scripts/test_update_knockout.py
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

def real_matches():
    return json.loads((ROOT / "data" / "matches.json").read_text(encoding="utf-8"))

# 国家字典:从真实小组赛行构建(稳定,不受淘汰赛回填影响)
cdict = U.build_dict(real_matches())

# 自造占位淘汰赛槽(与真实赛程解耦):各自不同的日期+球场,便于按"同日+球场"唯一匹配
def kslot(n, ko, venue):
    return {"n": n, "sk": "round-of-32", "st": "32强赛", "g": None,
            "h": "Group A runners-up", "a": "Group B runners-up",
            "hz": "A组第2", "az": "B组第2", "hf": "", "af": "", "c": "测试城", "v": venue, "ko": ko}
def ev(home, away, ko, venue, state="pre"):
    return {"competitions": [{"date": ko, "venue": {"fullName": venue},
            "status": {"type": {"state": state}},
            "competitors": [{"homeAway": "home", "team": {"displayName": home}},
                            {"homeAway": "away", "team": {"displayName": away}}]}]}
def slot(ms, n): return next(m for m in ms if m["n"] == n)

print("测试 0 · 国家字典(真实数据,稳定):")
ok(cdict.get(U.canon("Mexico")) == ("墨西哥", "🇲🇽"), "Mexico→🇲🇽墨西哥")
ok(cdict.get(U.canon("Brazil")) == ("巴西", "🇧🇷"), "Brazil→🇧🇷巴西")
ok(len(real_matches()) == 104, "真实赛程仍 104 场")

# ── 测试 1:回填正确(含别名 + 变音符号)──────────────────────────────
print("测试 1 · 回填正确(别名 + 变音符号):")
fix = [kslot(901, "2026-07-01T19:00:00Z", "场地A"),
       kslot(902, "2026-07-02T19:00:00Z", "场地B"),
       kslot(903, "2026-07-03T19:00:00Z", "场地C"),
       kslot(904, "2026-07-04T19:00:00Z", "场地D")]   # 无对应赛事 → 应保持占位
payload = {"events": [
    ev("Mexico", "Brazil", "2026-07-01T19:00:00Z", "场地A"),
    ev("South Korea", "USA", "2026-07-02T19:00:00Z", "场地B"),     # 别名
    ev("Türkiye", "France", "2026-07-03T19:00:00Z", "场地C"),      # 变音符号
    ev("TBD", "TBD", "2026-07-01T19:00:00Z", "场地A"),             # 应跳过
]}
changes = U.apply_updates(fix, U.parse_events(payload), cdict, [])
ok(changes == 3, "回填 3 场(TBD 跳过),实际 %d" % changes)
ok((slot(fix,901)["hz"], slot(fix,901)["hf"]) == ("墨西哥", "🇲🇽"), "901 主=🇲🇽墨西哥")
ok((slot(fix,901)["az"], slot(fix,901)["af"]) == ("巴西", "🇧🇷"), "901 客=🇧🇷巴西")
ok((slot(fix,902)["hz"], slot(fix,902)["hf"]) == ("韩国", "🇰🇷"), "902 别名 South Korea→🇰🇷韩国")
ok((slot(fix,902)["az"], slot(fix,902)["af"]) == ("美国", "🇺🇸"), "902 别名 USA→🇺🇸美国")
ok((slot(fix,903)["hz"], slot(fix,903)["hf"]) == ("土耳其", "🇹🇷"), "903 变音 Türkiye→🇹🇷土耳其")
ok(not (slot(fix,904)["hf"] and slot(fix,904)["af"]), "904 无对应赛事 → 仍占位")

# ── 测试 2:幂等(再跑一次不应再改)────────────────────────────────
print("测试 2 · 幂等:")
ok(U.apply_updates(fix, U.parse_events(payload), cdict, []) == 0, "第二次回填 0 场")

# ── 测试 3:只算已完赛由 parse_events 控制?此处验证已填的真实槽不被覆盖 ──
print("测试 3 · 已填的槽不被覆盖:")
fix2 = [dict(kslot(905, "2026-07-05T19:00:00Z", "场地E"),
             **{"h": "Spain", "a": "Italy", "hz": "西班牙", "az": "意大利", "hf": "🇪🇸", "af": "🇮🇹"})]
U.apply_updates(fix2, U.parse_events({"events": [ev("Mexico", "Brazil", "2026-07-05T19:00:00Z", "场地E")]}), cdict, [])
ok((slot(fix2,905)["hz"], slot(fix2,905)["az"]) == ("西班牙", "意大利"), "已确定的对阵不被改写")

# ── 测试 4:TBD / 未识别队名跳过 ──────────────────────────────────
print("测试 4 · TBD / 未识别队名跳过:")
fix3 = [kslot(906, "2026-07-06T19:00:00Z", "场地F")]
ok(U.apply_updates(fix3, U.parse_events({"events": [ev("Atlantis", "Wakanda", "2026-07-06T19:00:00Z", "场地F")]}), cdict, []) == 0,
   "未知国家不回填")
ok(not (slot(fix3,906)["hf"]), "槽保持占位")

# ── 测试 5:变音符号 canon 等价(稳定)──────────────────────────────
print("测试 5 · 变音符号 canon 等价:")
ok(U.canon("Türkiye") == U.canon("Turkiye"), "Türkiye ≡ Turkiye")
ok(U.canon("Côte d'Ivoire") == U.canon("Cote d'Ivoire"), "Côte d'Ivoire ≡ Cote d'Ivoire")
ok(U.canon("Curaçao") == U.canon("Curacao"), "Curaçao ≡ Curacao")

if fail:
    print("\n❌ %d 个断言失败" % fail); sys.exit(1)
print("\n✅ 全部通过")
