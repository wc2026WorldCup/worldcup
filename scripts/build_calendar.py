#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 data/matches.json,生成可订阅的 Apple 日历文件 worldcup.ics。

每场比赛生成两条日程:
  1) 比赛   —— 两道提醒:赛前 15 分钟、开球时
  2) 赛果   —— 开球后约 2 小时(小组赛 +135 分钟 / 淘汰赛 +180 分钟)一道提醒

所有时间以 UTC 写入(DTSTART/DTEND 带 Z);Apple 日历会自动换算成用户设备所在时区显示。

用法:
    python scripts/build_calendar.py

依赖:仅 Python 标准库。
"""
import json
import datetime
from datetime import timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "matches.json"
OUT  = ROOT / "worldcup.ics"

# 日程内的链接(指向网页)。?from=cal 用于在网页统计里区分“从日历点进来的”访问。
WEB = "https://wc2026worldcup.github.io/worldcup/?from=cal"


# ---- iCalendar 文本工具 ----
def esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def fmt(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")

def fold(line: str) -> str:
    """按 RFC 5545 折行(每行 ≤75 字节,续行以空格开头),按字节计避免截断多字节中文/emoji。"""
    out, cur, cb, first = [], "", 0, True
    for ch in line:
        b = len(ch.encode("utf-8"))
        lim = 75 if first else 74
        if cb + b > lim:
            out.append(cur); cur = " " + ch; cb = 1 + b; first = False
        else:
            cur += ch; cb += b
    out.append(cur)
    return "\r\n".join(out)

def team(flag: str, zh: str) -> str:
    # 小组赛:带国旗,如 “🇲🇽 墨西哥”;淘汰赛占位:无国旗,如 “A组第2”
    return (flag + " " + zh).strip()


def build() -> str:
    matches = sorted(json.load(open(DATA, encoding="utf-8")), key=lambda m: m["n"])
    dtstamp = fmt(datetime.datetime.now(timezone.utc))

    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WC2026 Sub//ZH//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:世界杯2026 ⚽", "NAME:世界杯2026 ⚽",
         "X-WR-CALDESC:2026世界杯 全104场 · 赛前15分钟+开球+赛果提醒(订阅版,淘汰赛对阵自动更新)",
         # 提示订阅端的刷新频率(12 小时);iOS/macOS 会据此定期回源拉取更新
         "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]

    def add(uid, summary, start, end, desc, alarms):
        L.extend(["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{dtstamp}",
                  f"DTSTART:{fmt(start)}", f"DTEND:{fmt(end)}",
                  fold("SUMMARY:" + esc(summary)), fold("DESCRIPTION:" + desc), f"URL:{WEB}"])
        for trig, txt in alarms:
            L.extend(["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:{trig}",
                      fold("DESCRIPTION:" + esc(txt)), "END:VALARM"])
        L.append("END:VEVENT")

    for m in matches:
        n = m["n"]
        ko = datetime.datetime.strptime(m["ko"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        knock = m["sk"] != "group-stage"
        after = 180 if knock else 135           # 赛果提醒相对开球的偏移(淘汰赛可能加时,留更久)
        home, away = team(m["hf"], m["hz"]), team(m["af"], m["az"])
        st  = m["st"]
        grp = f"{m['g']}组 · " if m.get("g") else ""
        link = f"👉 看比分与后续赛程：\\n{WEB}"

        # 比赛日程
        mt = f"🏆 {st}｜{home} vs {away}" if knock else f"{home} vs {away}"
        mdesc = f"{grp}{st}\\n📍 {esc(m['c'])} · {esc(m['v'])}\\n第{n}场/共104场\\n{link}"
        add(f"wc2026-match-{n}@worldcup.local", mt, ko, ko + timedelta(minutes=after), mdesc,
            [("-PT15M", f"⏰ 15分钟后开球：{mt}"), ("PT0M", f"🟢 开球：{mt}")])

        # 赛果日程
        rstart = ko + timedelta(minutes=after)
        rt = f"📊 赛果｜{st}：{home} vs {away}" if knock else f"📊 赛果｜{home} vs {away}"
        rdesc = f"{grp}{st} 已结束\\n{link}"
        add(f"wc2026-result-{n}@worldcup.local", rt, rstart, rstart + timedelta(minutes=10), rdesc,
            [("PT0M", rt)])

    L.append("END:VCALENDAR")
    out = "\r\n".join(L) + "\r\n"
    OUT.write_text(out, encoding="utf-8")
    print(f"✓ worldcup.ics 生成完毕：{out.count('BEGIN:VEVENT')} 条日程, "
          f"{out.count('BEGIN:VALARM')} 道提醒, {len(out.encode('utf-8'))} 字节")
    return out


if __name__ == "__main__":
    build()
