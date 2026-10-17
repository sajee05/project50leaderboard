"""Daily study leaderboard: Google Sheet -> HTML -> PNG -> Telegram topic."""
import csv, io, os, re, sys, html, datetime as dt
from zoneinfo import ZoneInfo
import requests

SHEET_ID = os.environ.get("SHEET_ID", "1ZlfTZ0e6oC65e85KXr-X6ZzuL4GQa-r5AcqCsQNCNeU")
GID = os.environ.get("SHEET_GID", "0")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "-1004340341673")      # from t.me/c/4340341673/...
THREAD_ID = os.environ.get("THREAD_ID", "1150")            # from .../1150
DAILY_TARGET_H = float(os.environ.get("DAILY_TARGET_H", "8"))
WEEKLY_TARGET_H = float(os.environ.get("WEEKLY_TARGET_H", "50"))
ONTRACK_AVG_H = float(os.environ.get("ONTRACK_AVG_H", "8"))   # avg/day >= this -> ON TRACK
ATRISK_AVG_H = float(os.environ.get("ATRISK_AVG_H", "7"))     # avg/day >= this -> AT RISK, else UNLIKELY
DAY_OVERRIDE = os.environ.get("DAY")                       # optional: force day number (1-7)
DRY = "--dry" in sys.argv


# ---------- parsing ----------
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
    mins = int(round(mins))
    return f"{mins // 60}:{mins % 60:02d}"


def parse_date(s):
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    return None


def find_cycle_start(rows):
    env = os.environ.get("CYCLE_START", "").strip()
    if env:
        return parse_date(env)
    for row in rows:
        for i, c in enumerate(row):
            if c.strip().lower().startswith("cycle start"):
                for nxt in row[i + 1:]:
                    if nxt.strip():
                        d = parse_date(nxt)
                        if d:
                            return d
                        break
    return None


def fetch_rows():
    url = os.environ.get("SHEET_CSV_URL", "").strip() or \
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
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
        return vals.json().get("values", [])
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return list(csv.reader(io.StringIO(r.text)))


def parse(rows):
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
    start = find_cycle_start(rows)
    n = len(day_cols)
    dates = [start + dt.timedelta(days=i) for i in range(n)] if start else None
    return people, dates, n


def pick_day(people, n_days, dates=None, now=None):
    if DAY_OVERRIDE:
        return int(DAY_OVERRIDE) - 1
    if dates:  # follow the real calendar date: 17 Oct with cycle start 12 Oct -> Day 6
        return max(0, min(n_days - 1, (now.date() - dates[0]).days))
    for d in range(n_days - 1, -1, -1):
        if any(p["mins"][d] for p in people):
            return d
    return 0


def status_of(total, avg):
    if total >= WEEKLY_TARGET_H * 60:
        return "DONE", "done"
    if avg >= ONTRACK_AVG_H * 60:
        return "ON TRACK", "on"
    if avg >= ATRISK_AVG_H * 60:
        return "AT RISK", "risk"
    return "UNLIKELY", "no"


# ---------- image ----------
CSS = """
*{box-sizing:border-box}
body{margin:0;padding:34px;width:1180px;background:#f6f7fb;color:#111827;
 font-family:Inter,'Segoe UI','Liberation Sans',Arial,sans-serif}
.head{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px}
h1{margin:0;font-size:32px;letter-spacing:-.5px}
.sub{color:#6b7280;font-size:16px;margin-top:4px}
.pill{background:#111827;color:#fff;border-radius:999px;padding:8px 16px;font-size:15px;font-weight:600}
.cards{display:flex;gap:18px;margin-bottom:20px}
.card{flex:1;background:#fff;border-radius:16px;padding:16px 20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h2{margin:0 0 10px;font-size:15px;text-transform:uppercase;letter-spacing:1px;color:#6b7280}
.top{display:flex;align-items:center;padding:6px 0;font-size:20px}
.top .nm{flex:1;font-weight:700;margin-left:12px}.top .tm{font-weight:800;font-variant-numeric:tabular-nums}
.badge{width:30px;height:30px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
 font-weight:800;font-size:15px;color:#111827;background:#e5e7eb}
.b1{background:#fbbf24}.b2{background:#d1d5db}.b3{background:#e0a46b}
table{width:100%;border-collapse:separate;border-spacing:0;background:#fff;border-radius:16px;overflow:hidden;
 box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:17px}
th{background:#111827;color:#fff;padding:11px 6px;font-size:14px;font-weight:600;line-height:1.25}
th small{display:block;font-weight:400;opacity:.65;font-size:12px}
th.today{background:#2563eb}
td{padding:7px 6px;text-align:center;border-bottom:1px solid #eef0f4;font-variant-numeric:tabular-nums}
tr:nth-child(even) td{background:#fafbfd}
td.nm{text-align:left;font-weight:700;padding-left:8px}
td.rk{width:46px}
td.col-today{box-shadow:inset 2px 0 0 #bfdbfe,inset -2px 0 0 #bfdbfe}
.c{display:inline-block;min-width:58px;padding:3px 0;border-radius:8px;font-weight:600}
.g{background:#d1fae5;color:#065f46}.a{background:#fef3c7;color:#92400e}.r{background:#fee2e2;color:#991b1b}
.z{color:#c0c4cc}.off{color:#9ca3af;font-style:italic}
td.tot{text-align:left;min-width:150px;padding-left:12px}
.tot b{font-size:18px}
.bar{height:7px;background:#e5e7eb;border-radius:4px;margin-top:5px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px}
.s-done{background:#10b981}.s-on{background:#3b82f6}.s-risk{background:#f59e0b}.s-no{background:#ef4444}
.st{display:inline-block;min-width:104px;padding:5px 0;border-radius:8px;font-weight:800;font-size:14px;letter-spacing:.3px}
.st.done{background:#d1fae5;color:#065f46}.st.on{background:#dbeafe;color:#1e40af}
.st.risk{background:#fef3c7;color:#92400e}.st.no{background:#fee2e2;color:#991b1b}
tr.sum td{background:#f3f4f6;font-weight:800;border-bottom:none}
.legend{margin-top:14px;font-size:14px;color:#6b7280;display:flex;justify-content:space-between}
"""


def build_html(people, dates, n_days, today, now):
    wt = int(WEEKLY_TARGET_H * 60)
    dtm = int(DAILY_TARGET_H * 60)
    elapsed = today + 1
    for p in people:
        p["avg"] = p["total"] / elapsed
        p["status"], p["scls"] = status_of(p["total"], p["avg"])
    ranked = sorted(people, key=lambda p: -p["total"])
    e = html.escape

    def dlabel(i):
        return dates[i].strftime("%d %b") if dates else ""

    head = "".join(
        f"<th class='{'today' if d == today else ''}'>Day {d + 1}<small>{dlabel(d)}</small></th>"
        for d in range(n_days))

    rows = ""
    for i, p in enumerate(ranked, 1):
        cells = ""
        for d in range(n_days):
            m, raw = p["mins"][d], p["raw"][d].strip()
            ct = " col-today" if d == today else ""
            if m > 0:
                k = "g" if m >= dtm else "a" if m >= dtm / 2 else "r"
                inner = f"<span class='c {k}'>{fmt(m)}</span>"
            elif raw.lower() == "off":
                inner = "<span class='off'>off</span>"
            else:
                inner = "<span class='z'>&ndash;</span>"
            cells += f"<td class='{ct.strip()}'>{inner}</td>"
        pct = min(100, p["total"] / wt * 100)
        rows += (
            f"<tr><td class='rk'><span class='badge b{i if i <= 3 else 0}'>{i}</span></td>"
            f"<td class='nm'>{e(p['name'])}</td>{cells}"
            f"<td class='tot'><b>{fmt(p['total'])}</b><span style='color:#9ca3af'> / {WEEKLY_TARGET_H:g}h</span>"
            f"<div class='bar'><i class='s-{p['scls']}' style='width:{pct:.1f}%'></i></div></td>"
            f"<td>{fmt(p['avg'])}</td>"
            f"<td><span class='st {p['scls']}'>{p['status']}</span></td></tr>")
    tot_cells = "".join(f"<td>{fmt(sum(p['mins'][d] for p in people))}</td>" for d in range(n_days))
    rows += (f"<tr class='sum'><td></td><td class='nm'>Group total</td>{tot_cells}"
             f"<td class='tot'>{fmt(sum(p['total'] for p in people))}</td><td></td><td></td></tr>")

    def top3(items, key):
        out = ""
        for i, p in enumerate(items[:3], 1):
            out += (f"<div class='top'><span class='badge b{i}'>{i}</span>"
                    f"<span class='nm'>{e(p['name'])}</span><span class='tm'>{fmt(key(p))}</span></div>")
        return out

    by_day = sorted(people, key=lambda p: -p["mins"][today])
    day_title = f"Day {today + 1}" + (f" &middot; {dates[today].strftime('%d %b')}" if dates else "")
    cycle = f"{dates[0].strftime('%d %b')} &ndash; {dates[-1].strftime('%d %b')}" if dates else ""
    return f"""<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>
<div class='head'><div><h1>Study Accountability Tracker</h1>
<div class='sub'>Daily target {DAILY_TARGET_H:g}h &middot; Weekly target {WEEKLY_TARGET_H:g}h &middot; Updated {now.strftime('%d %b %Y')}</div></div>
<div class='pill'>{cycle} &nbsp;|&nbsp; Day {elapsed} of {n_days}</div></div>
<div class='cards'>
<div class='card'><h2>Top 3 &middot; {day_title}</h2>{top3(by_day, lambda p: p['mins'][today])}</div>
<div class='card'><h2>Top 3 &middot; This week</h2>{top3(ranked, lambda p: p['total'])}</div></div>
<table><tr><th>#</th><th style='text-align:left'>Name</th>{head}<th>Weekly total</th><th>Avg/day</th><th>Status</th></tr>{rows}</table>
<div class='legend'><span>Day cells: green = {DAILY_TARGET_H:g}h+ &middot; amber = {DAILY_TARGET_H / 2:g}-{DAILY_TARGET_H:g}h &middot; red = under {DAILY_TARGET_H / 2:g}h</span>
<span>DONE = {WEEKLY_TARGET_H:g}h &middot; ON TRACK = avg {ONTRACK_AVG_H:g}h+ &middot; AT RISK = avg {ATRISK_AVG_H:g}h+ &middot; UNLIKELY = below</span></div>
</body></html>"""


# ---------- caption (Telegram HTML) ----------
def caption(people, today, now):
    e = html.escape
    td = sorted(people, key=lambda p: -p["mins"][today])[:3]
    wk = sorted(people, key=lambda p: -p["total"])[:3]
    d = now.day
    suffix = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    date_s = f"{d}{suffix} {now.strftime('%B, %A')}"
    medals = ["🥇", "🥈", "🥉"]
    t = "\n".join(f"{medals[i]} #{i + 1} {e(p['name'])} - <b>{fmt(p['mins'][today])}</b>" for i, p in enumerate(td))
    w = "\n".join(f"{medals[i]} #{i + 1} {e(p['name'])} - <b>{fmt(p['total'])}</b>" for i, p in enumerate(wk))
    best = list(dict.fromkeys([td[0]["name"], wk[0]["name"], wk[1]["name"]]))
    return (f"<b>{date_s}</b>. Y'all did great :)\n\n"
            f"<b>Top 3 Today</b>\n{t}\n\n"
            f"<b>Top 3 this week</b>\n{w}\n\n"
            f"<b>Highest chance of making it to the list in the group</b> = <b>{e(', '.join(best))}</b>")


def main():
    from playwright.sync_api import sync_playwright
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    people, dates, n_days = parse(fetch_rows())
    today = pick_day(people, n_days, dates, now)
    page_html = build_html(people, dates, n_days, today, now)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1250, "height": 900}, device_scale_factor=2)
        pg.set_content(page_html)
        pg.screenshot(path="leaderboard.png", full_page=True)
        b.close()
    cap = caption(people, today, now)
    print(cap)
    if DRY:
        return
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": CHAT_ID, "message_thread_id": THREAD_ID, "caption": cap, "parse_mode": "HTML"},
        files={"photo": open("leaderboard.png", "rb")}, timeout=60)
    print(r.status_code, r.text)
    r.raise_for_status()


if __name__ == "__main__":
    main()
