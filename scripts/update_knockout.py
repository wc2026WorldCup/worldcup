#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分组赛结束后,自动把淘汰赛的真实对阵回填进 data/matches.json(零人工)。

原理:
  从 ESPN 公开 scoreboard 接口按淘汰赛日期拉取赛事,用「同一天 + 开球时间最接近
  (+ 球场名匹配)」把每场 ESPN 赛事对应到我们数据里的淘汰赛占位槽,再用小组赛行
  建立的「国家 → 中文名 / 国旗 emoji」字典回填真实队名。
  - 只回填仍是占位(无国旗)的淘汰赛槽;已填的不动 → 幂等、可反复跑。
  - 任一队伍仍是 TBD / 无法识别 → 跳过该场,等下次。
  - 网络异常 → 不报错、不改动(exit 0),交给下次定时任务。
  随着每一轮打完,ESPN 会陆续给出下一轮真实对阵,本脚本每天定时跑就能逐轮自动填满,
  直到决赛。配合 build.yml:data 一变就自动重建网页与日历,订阅日历也会自动刷新。

用法:
  python scripts/update_knockout.py                 # 实跑(GitHub Actions 用)
  python scripts/update_knockout.py --mock x.json   # 用本地 ESPN 样本(测试用)
  python scripts/update_knockout.py --dry-run       # 只打印将要的改动,不写文件

仅 Python 标准库。
"""
import json, sys, re, urllib.request, datetime, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "matches.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={}"

KNOCK = {"round-of-32", "round-of-16", "quarter-finals", "semi-finals", "third-place", "final"}

# ESPN 队名 → 我们数据里的英文名(canon 后),与前端 template.html 的 ALIAS 保持一致
ALIAS = {
    "southkorea": "korearepublic", "korea": "korearepublic", "republicofkorea": "korearepublic",
    "turkey": "turkiye", "usa": "unitedstates", "unitedstatesofamerica": "unitedstates", "us": "unitedstates",
    "iran": "iriran", "capeverde": "caboverde", "ivorycoast": "cotedivoire",
    "drcongo": "congodr", "democraticrepublicofthecongo": "congodr", "congokinshasa": "congodr", "congo": "congodr",
    "bosnia": "bosniaandherzegovina", "bosniaherzegovina": "bosniaandherzegovina", "bih": "bosniaandherzegovina",
    "czechrepublic": "czechia", "czech": "czechia", "saudi": "saudiarabia", "uzbek": "uzbekistan",
}
TBD = {"", "tbd", "tobedetermined", "tba", "winner", "loser", "thirdplace"}


def norm(s):
    # 先去变音符号(Türkiye→Turkiye、Côte d'Ivoire→Cote...、Curaçao→Curacao),与前端 JS 的 NFD 对齐
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)

def canon(s):
    n = norm(s)
    return ALIAS.get(n, n)

def parse_ko(iso):
    """ESPN 时间(可能无秒、带 Z 或偏移)→ aware UTC datetime。"""
    if not iso:
        return None
    s = iso.strip().replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
        except Exception:
            pass
    return None

def our_ko(m):
    return datetime.datetime.strptime(m["ko"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

def build_dict(matches):
    """从小组赛行建立 canon(英文) → (中文名, 国旗 emoji)。"""
    d = {}
    for m in matches:
        if m.get("sk") == "group-stage":
            d[canon(m["h"])] = (m["hz"], m["hf"])
            d[canon(m["a"])] = (m["az"], m["af"])
    return d

def parse_events(espn_json):
    """ESPN scoreboard JSON → [{home, away, ko, venue, state}],含两支球队的赛事。"""
    out = []
    for ev in (espn_json or {}).get("events", []):
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        cs = comp.get("competitors") or []
        if len(cs) < 2:
            continue
        H = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
        A = next((c for c in cs if c.get("homeAway") == "away"), cs[1])
        def nm(c):
            t = c.get("team") or {}
            return t.get("displayName") or t.get("name") or t.get("shortDisplayName") or ""
        out.append({
            "home": nm(H), "away": nm(A),
            "ko": parse_ko(comp.get("date") or ev.get("date") or ""),
            "venue": ((comp.get("venue") or {}).get("fullName")) or "",
            "state": ((((comp.get("status") or {}).get("type")) or {}).get("state") or "").lower(),
        })
    return out

def apply_updates(matches, events, cdict, log=None):
    """把 ESPN 赛事回填到仍为占位的淘汰赛槽。返回回填场数。纯函数,可单测。"""
    if log is None:
        log = []
    allk = [m for m in matches if m.get("sk") in KNOCK]
    known = lambda m: bool(m.get("hf") and m.get("af"))   # 队伍已确定
    used = set()
    changes = 0
    for ev in events:
        if norm(ev["home"]) in TBD or norm(ev["away"]) in TBD:
            continue
        ch, ca = canon(ev["home"]), canon(ev["away"])
        if ch not in cdict or ca not in cdict:
            log.append("跳过(队名未识别): %s vs %s" % (ev["home"], ev["away"]))
            continue
        if ev["ko"] is None:
            continue
        day = ev["ko"].date()
        pool = [m for m in allk if our_ko(m).date() == day]          # 同一 UTC 日的所有淘汰赛槽
        if not pool and norm(ev["venue"]):                           # 跨日兜底:必须球场吻合
            pool = [m for m in allk if norm(ev["venue"]) == norm(m["v"])
                    and abs((our_ko(m) - ev["ko"]).total_seconds()) <= 36 * 3600]
        if not pool:
            continue
        def rank(m):  # 球场匹配优先,再按开球时间最接近
            return (0 if (ev["venue"] and norm(ev["venue"]) == norm(m["v"])) else 1,
                    abs((our_ko(m) - ev["ko"]).total_seconds()))
        cand = sorted(pool, key=rank)[0]                             # 该场对应的唯一最佳槽
        if cand["n"] in used or known(cand):                        # 已就位 → 幂等跳过
            continue
        # 时间差超 6h 且球场也不符 → 不放心,跳过(保守)
        if abs((our_ko(cand) - ev["ko"]).total_seconds()) > 6 * 3600 and norm(ev["venue"]) != norm(cand["v"]):
            log.append("跳过(无法可靠匹配): %s vs %s @ %s" % (ev["home"], ev["away"], ev["ko"]))
            continue
        zhH, flH = cdict[ch]
        zhA, flA = cdict[ca]
        cand["h"], cand["hz"], cand["hf"] = ev["home"], zhH, flH
        cand["a"], cand["az"], cand["af"] = ev["away"], zhA, flA
        used.add(cand["n"])
        changes += 1
        log.append("回填 第%d场 %s:%s%s vs %s%s" % (cand["n"], cand["st"], flH, zhH, flA, zhA))
    return changes

def knockout_dates(matches):
    ds = set()
    for m in matches:
        if m.get("sk") in KNOCK:
            d = our_ko(m)
            for off in (-1, 0, 1):  # 含相邻日,兜 ESPN 日期分桶差异
                ds.add((d + datetime.timedelta(days=off)).strftime("%Y%m%d"))
    return sorted(ds)

def fetch_espn(dates):
    payloads = []
    for d in dates:
        try:
            req = urllib.request.Request(ESPN.format(d), headers={"User-Agent": "wc2026-update/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                payloads.append(json.loads(r.read().decode("utf-8")))
        except Exception as e:
            print("  · 拉取 %s 失败:%s" % (d, e))
    return payloads

def main(argv):
    dry = "--dry-run" in argv
    mock = argv[argv.index("--mock") + 1] if "--mock" in argv else None

    matches = json.loads(DATA.read_text(encoding="utf-8"))
    cdict = build_dict(matches)

    if mock:
        payloads = [json.loads(Path(mock).read_text(encoding="utf-8"))]
    else:
        payloads = fetch_espn(knockout_dates(matches))

    events = []
    for p in payloads:
        events += parse_events(p)

    log = []
    changes = apply_updates(matches, events, cdict, log)
    for line in log:
        print("  ", line)

    if changes and not dry:
        DATA.write_text(json.dumps(matches, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print("✓ 回填 %d 场淘汰赛对阵,已写入 data/matches.json" % changes)
    elif changes:
        print("(dry-run)将回填 %d 场,未写文件" % changes)
    else:
        print("无可回填的淘汰赛对阵(小组赛可能未结束,或已全部填好)。")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
