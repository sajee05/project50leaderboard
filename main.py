"""Daily study leaderboard: Google Sheet -> HTML -> PNG (16:9) -> Telegram topic."""
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


# ---------- image: 16:9, Today (left) | This week (right) ----------
CSS = """*{box-sizing:border-box}
:root{--bg:#f5f5f7;--card:#fff;--tx:#1d1d1f;--mu:#86868b;--chip:#f2f2f5;--ln:#efeff2;--tk:#ececf0;
--tdy:rgba(10,132,255,.07);--gb:rgba(52,199,89,.16);--gt:#17803a;--ab:rgba(255,159,10,.18);--at:#b25e00;
--rb:rgba(255,59,48,.13);--rt:#c4271c;--bb:rgba(10,132,255,.13);--bt:#0a63c9}
body{margin:0;width:1920px;height:1080px;padding:34px;background:var(--bg);color:var(--tx);
font-family:-apple-system,'SF Pro Display',Inter,'Helvetica Neue','Liberation Sans',Arial,sans-serif;
display:flex;flex-direction:column;gap:14px}
.wrap{flex:1;display:flex;gap:22px;min-height:0}
.panel{background:var(--card);border-radius:30px;padding:26px 30px 14px;display:flex;flex-direction:column;box-shadow:0 2px 24px rgba(0,0,0,.05)}
.pl{width:680px}.pr{flex:1}
.ph{display:flex;justify-content:space-between;align-items:flex-start}h1{margin:0;font-size:42px;letter-spacing:-1.1px}
.sub{font-size:17px;color:var(--mu);margin-top:3px}
.pill{background:var(--tx);color:var(--bg);border-radius:999px;padding:8px 16px;font-size:15px;font-weight:600;margin-top:6px}
.chips{display:flex;gap:10px;margin:14px 0 10px}
.chip{flex:1;background:var(--chip);border-radius:16px;padding:10px 14px;display:flex;align-items:center;font-size:19px}
.chip:first-child{background:var(--tx);color:var(--bg)}.cn{flex:1;font-weight:700;margin-left:10px}.ct{font-weight:800;font-variant-numeric:tabular-nums}
.bd{width:26px;height:26px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;background:var(--chip);color:var(--tx);flex:none;margin-right:4px}
.chip:first-child .bd{background:var(--bg);color:var(--tx)}
.b1{background:#fbbf24!important;color:#1d1d1f!important}.b2{background:#d1d5db!important;color:#1d1d1f!important}.b3{background:#e0a46b!important;color:#1d1d1f!important}
.th,.row{display:flex;align-items:center}
.th{font-size:13px;color:var(--mu);font-weight:600;height:40px;border-bottom:1px solid var(--ln)}
.th small,.dc small{display:block;font-weight:400;font-size:11px;opacity:.7}
.row{flex:1;border-bottom:1px solid var(--ln);font-size:18px;max-height:42px}.row.sum{font-weight:800;border-bottom:none}
.nm{width:130px;font-weight:600}.pr .nm{width:112px}
.dc{width:70px;text-align:center;flex:none;padding:2px 0}.dc.tdy{background:var(--tdy);border-radius:10px}.th .dc.tdy{color:#0a84ff;font-weight:700}
.c{display:inline-block;min-width:56px;padding:3px 0;border-radius:8px;font-weight:600;font-size:16px;font-variant-numeric:tabular-nums}
.c.g,.tm.g{background:var(--gb);color:var(--gt)}.c.a,.tm.a{background:var(--ab);color:var(--at)}.c.r,.tm.r{background:var(--rb);color:var(--rt)}
.z{color:var(--mu);opacity:.5;font-style:normal}.off{color:var(--mu);font-size:14px}
.tr{flex:1;height:10px;border-radius:5px;background:var(--tk);margin:0 16px;position:relative}.tr i{display:block;height:100%;border-radius:5px}
.fg{background:#34c759}.fa{background:#ff9f0a}.fr{background:#ff3b30}
.tm{width:80px;text-align:center;font-weight:700;border-radius:8px;padding:3px 0;font-variant-numeric:tabular-nums}
.tm.z{background:none}.row.sum .tm{background:none;color:var(--tx)}
.tot{width:190px;padding-left:14px;flex:none}.tot b{font-size:19px}.tot em{font-style:normal;color:var(--mu);font-size:14px}
.pb{display:block;height:6px;background:var(--tk);border-radius:3px;margin-top:4px;overflow:hidden}.pb i{display:block;height:100%}
.sdone{background:#34c759}.son{background:#0a84ff}.srisk{background:#ff9f0a}.sno{background:#ff3b30}
.av{width:78px;text-align:center;flex:none;font-variant-numeric:tabular-nums}.stw{width:124px;text-align:center;flex:none}
.st{display:inline-block;min-width:104px;padding:5px 0;border-radius:8px;font-size:13px;font-weight:800;letter-spacing:.3px}
.st.done{background:var(--gb);color:var(--gt)}.st.on{background:var(--bb);color:var(--bt)}
.st.risk{background:var(--ab);color:var(--at)}.st.no{background:var(--rb);color:var(--rt)}
.legend{display:flex;justify-content:space-between;font-size:14px;color:var(--mu);padding:0 8px}"""


def build_html(people, dates, n_days, today, now):
    e = html.escape
    dtm = int(DAILY_TARGET_H * 60)
    wt = int(WEEKLY_TARGET_H * 60)
    elapsed = today + 1
    for p in people:
        p["avg"] = p["total"] / elapsed
        p["st"], p["sc"] = status_of(p["total"], p["avg"])
    day = sorted(people, key=lambda p: -p["mins"][today])
    wk = sorted(people, key=lambda p: -p["total"])

    def k(x):
        return "g" if x >= dtm else "a" if x >= dtm / 2 else "r"

    def dstr(d, f):
        return dates[d].strftime(f) if dates else ""

    def chips(items):
        return "".join(
            f"<div class='chip'><span class='bd b{i}'>{i}</span><span class='cn'>{e(nm)}</span><span class='ct'>{v}</span></div>"
            for i, (nm, v) in enumerate(items, 1))

    # left: today
    lrows = ""
    for i, p in enumerate(day, 1):
        x = p["mins"][today]
        pct = min(100, x / dtm * 100)  # bar is full at the daily target (8h+)
        lrows += (f"<div class='row'><span class='bd b{i if i <= 3 else 0}'>{i}</span><span class='nm'>{e(p['name'])}</span>"
                  f"<span class='tr'><i class='f{k(x) if x else 'g'}' style='width:{pct:.1f}%'></i></span>"
                  f"<span class='tm {k(x) if x else 'z'}'>{fmt(x) if x else '&ndash;'}</span></div>")
    lrows += (f"<div class='row sum'><span class='bd'></span><span class='nm'>Group total</span>"
              f"<span class='tr' style='background:none'></span><span class='tm'>{fmt(sum(p['mins'][today] for p in people))}</span></div>")
    day_sub = (dstr(today, "%A, %d %b") + " &middot; " if dates else "") + f"Day {today + 1} of {n_days} &middot; target {DAILY_TARGET_H:g}h"
    left = (f"<div class='panel pl'><div class='ph'><div><h1>Today</h1><div class='sub'>{day_sub}</div></div></div>"
            f"<div class='chips'>{chips([(p['name'], fmt(p['mins'][today])) for p in day[:3]])}</div>"
            f"<div class='th'><span style='width:30px'></span><span style='width:130px'>Name</span>"
            f"<span style='flex:1'>Hours &middot; bar is full at {DAILY_TARGET_H:g}h</span></div>{lrows}</div>")

    # right: week
    hd = "".join(f"<span class='dc{' tdy' if d == today else ''}'>Day {d + 1}<small>{dstr(d, '%d %b')}</small></span>"
                 for d in range(n_days))
    rrows = ""
    for i, p in enumerate(wk, 1):
        cells = ""
        for d in range(n_days):
            x, raw = p["mins"][d], p["raw"][d].strip()
            t = " tdy" if d == today else ""
            if x:
                inner = f"<b class='c {k(x)}'>{fmt(x)}</b>"
            elif raw.lower() == "off":
                inner = "<i class='off'>off</i>"
            else:
                inner = "<i class='z'>&ndash;</i>"
            cells += f"<span class='dc{t}'>{inner}</span>"
        pct = min(100, p["total"] / wt * 100)  # bar is full at the weekly target (50h+)
        rrows += (f"<div class='row'><span class='bd b{i if i <= 3 else 0}'>{i}</span><span class='nm'>{e(p['name'])}</span>{cells}"
                  f"<span class='tot'><b>{fmt(p['total'])}</b><em> / {WEEKLY_TARGET_H:g}h</em>"
                  f"<span class='pb'><i class='s{p['sc']}' style='width:{pct:.1f}%'></i></span></span>"
                  f"<span class='av'>{fmt(p['avg'])}</span><span class='stw'><b class='st {p['sc']}'>{p['st']}</b></span></div>")
    gt = "".join(f"<span class='dc'>{fmt(sum(p['mins'][d] for p in people))}</span>" for d in range(n_days))
    rrows += (f"<div class='row sum'><span class='bd'></span><span class='nm'>Group total</span>{gt}"
              f"<span class='tot'><b>{fmt(sum(p['total'] for p in people))}</b></span><span class='av'></span><span class='stw'></span></div>")
    cycle = f"{dstr(0, '%d %b')} &ndash; {dstr(n_days - 1, '%d %b')} &middot; " if dates else ""
    right = (f"<div class='panel pr'><div class='ph'><div><h1>This week</h1>"
             f"<div class='sub'>Weekly target {WEEKLY_TARGET_H:g}h &middot; Updated {now.strftime('%d %b %Y')}</div></div>"
             f"<div class='pill'>{cycle}Day {elapsed} of {n_days}</div></div>"
             f"<div class='chips'>{chips([(p['name'], fmt(p['total'])) for p in wk[:3]])}</div>"
             f"<div class='th'><span style='width:30px'></span><span style='width:112px'>Name</span>{hd}"
             f"<span class='tot'>Weekly total</span><span class='av'>Avg/day</span><span class='stw'>Status</span></div>{rrows}</div>")

    legend = (f"<div class='legend'><span>Day cells: green = {DAILY_TARGET_H:g}h+ &middot; amber = {DAILY_TARGET_H / 2:g}&ndash;{DAILY_TARGET_H:g}h &middot; red = under {DAILY_TARGET_H / 2:g}h</span>"
              f"<span>DONE = {WEEKLY_TARGET_H:g}h &middot; ON TRACK = avg {ONTRACK_AVG_H:g}h+ &middot; AT RISK = avg {ATRISK_AVG_H:g}h+ &middot; UNLIKELY = below</span></div>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body><div class='wrap'>{left}{right}</div>{legend}</body></html>")


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
    # The study day runs 11:45 PM -> 11:45 PM (IST). Shifting the clock back 23h45m maps:
    # 11:45 PM on 17 Oct (or a late start after midnight) -> 17 Oct; 8:40 PM on 17 Oct -> 16 Oct.
    now = dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    people, dates, n_days = parse(fetch_rows())
    today = pick_day(people, n_days, dates, now)
    page_html = build_html(people, dates, n_days, today, now)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1.25)
        pg.set_content(page_html)
        pg.screenshot(path="leaderboard.png")
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
