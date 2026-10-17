"""Daily study leaderboard: Google Sheet -> HTML -> PNG -> Telegram topic."""
import csv, io, os, re, sys, html, datetime as dt
from zoneinfo import ZoneInfo
import requests
from playwright.sync_api import sync_playwright

SHEET_ID = os.environ.get("SHEET_ID", "1ZlfTZ0e6oC65e85KXr-X6ZzuL4GQa-r5AcqCsQNCNeU")
GID = os.environ.get("SHEET_GID", "0")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "-1004340341673")      # from t.me/c/4340341673/...
THREAD_ID = os.environ.get("THREAD_ID", "1150")            # from .../1150
DAILY_TARGET_H = float(os.environ.get("DAILY_TARGET_H", "8"))
WEEKLY_TARGET_H = float(os.environ.get("WEEKLY_TARGET_H", "50"))
DAY_OVERRIDE = os.environ.get("DAY")                       # optional: force day number (1-7)
DRY = "--dry" in sys.argv


def parse_minutes(v):
    v = (v or "").strip().lower()
    if not v or v in {"-", "off", "—"}:
        return 0
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::\d{1,2})?", v)
    if m:
        return int(m[1]) * 60 + int(m[2])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*h?", v)
    if m:
        return round(float(m[1]) * 60)
    return 0  # text like "Kal se"


def fmt(mins):
    return f"{mins // 60}:{mins % 60:02d}"


def load():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    sa_json = os.environ.get("GOOGLE_SA_JSON", "").strip()
    print("Service account secret present:", bool(sa_json))
    if sa_json:
        import json
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        creds = service_account.Credentials.from_service_account_info(
            json.loads(sa_json), scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        s = AuthorizedSession(creds)
        api = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        meta = s.get(api, params={"fields": "sheets.properties"}, timeout=60)
        if not meta.ok:
            raise SystemExit(f"Sheets API error {meta.status_code}: {meta.text}")
        sheets = [x["properties"] for x in meta.json()["sheets"]]
        tab = next((p for p in sheets if str(p["sheetId"]) == str(GID)), sheets[0])
        vals = s.get(f"{api}/values/{requests.utils.quote(chr(39) + tab['title'] + chr(39))}", timeout=60)
        if not vals.ok:
            raise SystemExit(f"Sheets API error {vals.status_code}: {vals.text}")
        rows = vals.json().get("values", [])
    else:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        rows = list(csv.reader(io.StringIO(r.text)))
    hdr_i = next(i for i, row in enumerate(rows) if any(c.strip().lower() == "name" for c in row))
    hdr = rows[hdr_i]
    name_c = next(i for i, c in enumerate(hdr) if c.strip().lower() == "name")
    day_cols = [i for i, c in enumerate(hdr) if re.match(r"\s*day\s*\d", c, re.I)]
    people = []
    for row in rows[hdr_i + 1:]:
        if len(row) <= name_c or not row[name_c].strip():
            continue
        name = row[name_c].strip()
        if name.lower() in {"total", "totals"}:
            continue
        raw = [row[c] if c < len(row) else "" for c in day_cols]
        mins = [parse_minutes(x) for x in raw]
        people.append({"name": name, "raw": raw, "mins": mins, "total": sum(mins)})
    labels = [hdr[c].strip() for c in day_cols]
    return people, labels


def pick_day(people, n_days):
    if DAY_OVERRIDE:
        return int(DAY_OVERRIDE) - 1
    for d in range(n_days - 1, -1, -1):
        if any(p["mins"][d] for p in people):
            return d
    return 0


def cls_day(m):
    return "g" if m >= DAILY_TARGET_H * 60 else "a" if m >= DAILY_TARGET_H * 30 else "r"


def cls_week(m):
    return "g" if m >= WEEKLY_TARGET_H * 48 else "a" if m >= WEEKLY_TARGET_H * 12 else "r"


def build_html(people, labels, today, now):
    ranked = sorted(people, key=lambda p: -p["total"])
    wt = WEEKLY_TARGET_H * 60
    dt_ = DAILY_TARGET_H * 60
    head = "".join(f"<th>Day {i+1}<br><small>{html.escape(re.sub(r'(?i)day\s*\d+\s*', '', l))}</small></th>"
                   for i, l in enumerate(labels))
    body = ""
    for i, p in enumerate(ranked, 1):
        medal = {1: "gold", 2: "silver", 3: "bronze"}.get(i, "")
        cells = ""
        for d, raw in enumerate(p["raw"]):
            txt = fmt(p["mins"][d]) if p["mins"][d] else (raw.strip() or "-")
            hi = " today" if d == today else ""
            cells += f"<td class='day{hi}'>{html.escape(txt)}</td>"
        short = max(0, wt - p["total"])
        done = p["total"] >= wt
        body += (f"<tr><td class='rk {medal}'>{i}</td><td class='nm'>{html.escape(p['name'])}</td>"
                 f"<td class='tg'>{DAILY_TARGET_H:g}h</td>{cells}<td><b>{fmt(p['total'])}</b></td>"
                 f"<td class='tg'>{WEEKLY_TARGET_H:g}h</td><td class='sb'>{'-' if done else fmt(short)}</td>"
                 f"<td class='{'ok' if done else 'no'}'>{'DONE' if done else 'NOT MET'}</td></tr>")
    tot_cells = "".join(f"<td>{fmt(sum(p['mins'][d] for p in people))}</td>" for d in range(len(labels)))
    body += (f"<tr class='tot'><td></td><td>TOTAL</td><td>-</td>{tot_cells}"
             f"<td>{fmt(sum(p['total'] for p in people))}</td><td>{WEEKLY_TARGET_H * len(people):g}h</td><td></td><td></td></tr>")

    by_day = sorted(people, key=lambda p: -p["mins"][today])
    dmax = max(dt_ * 1.5, by_day[0]["mins"][today])
    day_bars = "".join(
        f"<div class='row'><span>{html.escape(p['name'])}</span><div class='tr'><div class='bar {cls_day(p['mins'][today])}' "
        f"style='width:{p['mins'][today] / dmax * 100:.1f}%'></div><i style='left:{dt_ / dmax * 100:.1f}%'></i></div>"
        f"<b>{fmt(p['mins'][today]) if p['mins'][today] else 'Off'}</b></div>" for p in by_day)
    wk_bars = "".join(
        f"<div class='row'><span>{html.escape(p['name'])}</span><div class='tr'><div class='bar {cls_week(p['total'])}' "
        f"style='width:{min(100, p['total'] / wt * 100):.1f}%'></div></div><b>{fmt(p['total'])}</b></div>" for p in ranked)

    title_date = now.strftime("%d %b %Y")
    return f"""<html><head><meta charset='utf-8'><style>
body{{margin:0;padding:28px;background:#fff;font-family:Inter,Segoe UI,Arial,sans-serif;width:1500px;color:#111}}
h1{{font-size:26px;margin:0 0 14px}} table{{border-collapse:collapse;width:100%;font-size:17px}}
th{{background:#1f2937;color:#fff;padding:8px 6px;font-size:15px}} th small{{font-weight:400}}
td{{border:1px solid #cbd5e1;padding:7px 8px;text-align:center}} td.nm{{text-align:left;font-weight:600}}
td.day{{background:#fef7d6}} td.day.today{{background:#fde68a;font-weight:700}} td.tg{{color:#1d4ed8;font-weight:700}}
td.sb{{background:#e0e7ff}} td.ok{{background:#c6f6d5;color:#166534;font-weight:700}} td.no{{background:#fecaca;color:#991b1b;font-weight:700}}
td.rk.gold{{background:#ffd700}} td.rk.silver{{background:#e5e5e5}} td.rk.bronze{{background:#e8b887}}
tr.tot td{{background:#d9d9d9;font-weight:700}}
.charts{{display:flex;gap:28px;margin-top:26px}} .card{{flex:1;border:1px solid #cbd5e1;border-radius:10px;padding:14px 18px}}
.card h2{{font-size:18px;margin:0 0 10px;text-align:center}} .row{{display:flex;align-items:center;margin:4px 0;font-size:15px}}
.row span{{width:110px;text-align:right;padding-right:10px}} .row b{{width:60px;padding-left:8px}}
.tr{{flex:1;height:18px;position:relative;background:#f1f5f9}} .bar{{height:100%}} .g{{background:#2ca02c}} .a{{background:#f0a500}} .r{{background:#d62728}}
.tr i{{position:absolute;top:-3px;bottom:-3px;border-left:2px dashed #111}}
.legend{{font-size:13px;color:#555;margin-top:8px;text-align:center}}
</style></head><body>
<h1>Weekly Study Accountability Tracker - {title_date}</h1>
<table><tr><th>Rank</th><th>Name</th><th>Daily<br>Target</th>{head}<th>Weekly<br>Total</th><th>Weekly<br>Target</th><th>Short<br>By</th><th>Result</th></tr>{body}</table>
<div class='charts'>
<div class='card'><h2>Day {today + 1}: hours vs {DAILY_TARGET_H:g}h daily target</h2>{day_bars}
<div class='legend'>green = met target | amber = 4-8h | red = under 4h</div></div>
<div class='card'><h2>Weekly total vs {WEEKLY_TARGET_H:g}h goal</h2>{wk_bars}
<div class='legend'>green = 80%+ | amber = 20-80% | red = under 20%</div></div>
</div></body></html>"""


def caption(people, today, now):
    td = sorted(people, key=lambda p: -p["mins"][today])[:3]
    wk = sorted(people, key=lambda p: -p["total"])[:3]
    d = now.day
    suffix = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    date_s = f"{d}{suffix} {now.strftime('%B, %A')}"
    t = lambda i: f"#{i+1} {td[i]['name']} - {fmt(td[i]['mins'][today])}"
    w = lambda i: f"#{i+1} {wk[i]['name']} - {fmt(wk[i]['total'])}"
    best = list(dict.fromkeys([td[0]["name"], wk[0]["name"], wk[1]["name"]]))
    return (f"{date_s}. Y'all did great :)\n"
            f"Top 3 Today {t(0)} {t(1)} {t(2)}\n"
            f"And Top 3 this week {w(0)} {w(1)} {w(2)}\n"
            f"highest chance of making it to the list in the group = {', '.join(best)}")


def main():
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    people, labels = load()
    today = pick_day(people, len(labels))
    page_html = build_html(people, labels, today, now)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1560, "height": 900}, device_scale_factor=1.5)
        pg.set_content(page_html)
        pg.screenshot(path="leaderboard.png", full_page=True)
        b.close()
    cap = caption(people, today, now)
    print(cap)
    if DRY:
        return
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": CHAT_ID, "message_thread_id": THREAD_ID, "caption": cap},
        files={"photo": open("leaderboard.png", "rb")}, timeout=60)
    print(r.status_code, r.text)
    r.raise_for_status()


if __name__ == "__main__":
    main()
