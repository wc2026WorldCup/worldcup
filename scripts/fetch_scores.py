#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 ESPN 实时比分快照到 live/scores.json,作为「同源比分兜底」。

为什么需要:
  线上网页的实时比分靠浏览器直连 ESPN 公开接口;但部分网络(尤其中国大陆)可能直接
  连不上 ESPN,比分就会空白。本脚本由 GitHub Actions 定时在云端(可正常访问 ESPN)
  抓取比分,写入 live/scores.json;前端在 ESPN 直连失败时回退读这个同源文件 —— 至少
  能看到「最近一次更新」的比分,已结束比赛的结果也始终正确。

匹配方式:用「中文名/英文名 canon 后的两队组合」对到 data/matches.json 的场次号 n,
比分按该场主客方向归一(含 ESPN 的 winner 标志,淘汰赛点球也准)。复用 update_knockout 的工具。

用法:
  python scripts/fetch_scores.py                 # 实跑(GitHub Actions 用)
  python scripts/fetch_scores.py --mock x.json   # 用本地 ESPN 样本(测试用)
仅 Python 标准库。
"""
import json, sys, datetime, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_knockout as U   # 复用 canon / parse_ko / our_ko / ESPN

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "matches.json"
OUT  = ROOT / "live" / "scores.json"


def known(m):
    return bool(m.get("hf") and m.get("af"))   # 队伍已确定(小组赛恒真;淘汰赛回填后为真)

def pair_index(matches):
    """canon 两队组合 → 场次行(只含已确定队伍的场次)。"""
    idx = {}
    for m in matches:
        if known(m):
            idx[tuple(sorted((U.canon(m["h"]), U.canon(m["a"]))))] = m
    return idx

def ko_vd_index(matches):
    """淘汰赛「UTC日|球场」→ 场次行(与是否回填无关)。"""
    idx = {}
    for m in matches:
        if m.get("sk") in U.KNOCK:
            idx[U.our_ko(m).strftime("%Y%m%d") + "|" + U.norm(m["v"])] = m
    return idx

def parse_scores(payloads, idx, kovd=None, nat=None):
    """ESPN scoreboard 多份 JSON → {场次号 n: {...}}。纯函数,可单测。
    队名对得上 → {hs,as,live,w}(按我方主客归一);
    对不上但按 场地+日期 命中淘汰赛槽 → 额外带 {h,a,hz,az,hf,af}(以 ESPN 主客为准,供前端回填未确定的淘汰赛)。"""
    out = {}
    for j in payloads:
        for ev in (j or {}).get("events", []):
            comps = ev.get("competitions") or []
            if not comps:
                continue
            comp = comps[0]
            cs = comp.get("competitors") or []
            if len(cs) < 2:
                continue
            H = next((c for c in cs if c.get("homeAway") == "home"), cs[0])
            A = next((c for c in cs if c.get("homeAway") == "away"), cs[1])
            st = ((((comp.get("status") or {}).get("type")) or {}).get("state") or "").lower()
            if st not in ("in", "post"):
                continue
            def nm(c):
                t = c.get("team") or {}
                return t.get("displayName") or t.get("name") or t.get("shortDisplayName") or ""
            nH, nA = nm(H), nm(A)
            try:
                hs, as_ = int(H.get("score")), int(A.get("score"))
            except (TypeError, ValueError):
                continue
            w0 = 'h' if H.get("winner") is True else 'a' if A.get("winner") is True else None
            fx = idx.get(tuple(sorted((U.canon(nH), U.canon(nA)))))
            if fx:                                            # 按队名匹配 → 按我方主客归一
                hs2, as2, w = hs, as_, w0
                if U.canon(fx["h"]) != U.canon(nH):
                    hs2, as2 = as_, hs
                    w = 'a' if w0 == 'h' else 'h' if w0 == 'a' else None
                out[fx["n"]] = {"hs": hs2, "as": as2, "live": st == "in", "w": w}
            elif kovd is not None and nat is not None:        # 按场地+日期匹配未回填的淘汰赛,并带队伍
                ven = ((comp.get("venue") or {}).get("fullName")) or ""
                ko = U.parse_ko(comp.get("date") or ev.get("date") or "")
                if not ko:
                    continue
                kf = kovd.get(ko.strftime("%Y%m%d") + "|" + U.norm(ven))
                if not kf:
                    continue
                dH, dA = nat.get(U.canon(nH)), nat.get(U.canon(nA))
                if not dH or not dA:                          # 队名不识别 → 跳过,不存可能错位的比分
                    continue
                out[kf["n"]] = {"hs": hs, "as": as_, "live": st == "in", "w": w0,
                                "h": nH, "a": nA, "hz": dH[0], "hf": dH[1], "az": dA[0], "af": dA[1]}
    return out

def dates_for(matches):
    now = datetime.datetime.now(datetime.timezone.utc)
    ds = {now.strftime("%Y%m%d")}
    for m in matches:
        k = U.our_ko(m)
        if k < now - datetime.timedelta(days=2) or k > now + datetime.timedelta(days=1):
            continue
        for off in (-1, 0, 1):
            ds.add((k + datetime.timedelta(days=off)).strftime("%Y%m%d"))
    return sorted(ds)

def fetch(dates):
    ps = []
    for d in dates:
        try:
            req = urllib.request.Request(U.ESPN.format(d), headers={"User-Agent": "wc2026-scores/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ps.append(json.loads(r.read().decode("utf-8")))
        except Exception as e:
            print("  · 拉取 %s 失败:%s" % (d, e))
    return ps

def main(argv):
    mock = argv[argv.index("--mock") + 1] if "--mock" in argv else None
    matches = json.loads(DATA.read_text(encoding="utf-8"))
    idx = pair_index(matches)
    nat = U.build_dict(matches)          # canon 英文 → (中文名, 国旗)
    kovd = ko_vd_index(matches)          # 淘汰赛「日期|球场」索引
    payloads = [json.loads(Path(mock).read_text(encoding="utf-8"))] if mock else fetch(dates_for(matches))
    scores = parse_scores(payloads, idx, kovd, nat)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not scores and OUT.exists():                       # 全部拉取失败时,保留上次快照,别用空覆盖
        print("无新比分(可能拉取失败),保留现有快照。")
        return 0
    payload = {"updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "scores": {str(k): v for k, v in scores.items()}}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("✓ 写入 %d 场比分 → live/scores.json" % len(scores))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
