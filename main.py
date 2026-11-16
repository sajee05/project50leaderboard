"""Daily study leaderboard: Google Sheet -> HTML -> PNG (16:9) -> Telegram topic."""
import csv, io, os, re, sys, html, time, datetime as dt
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
ADMIN_IDS = {int(x) for x in re.split(r"[,\s]+", os.environ.get("ADMIN_IDS", "7574436736")) if x.strip()}  # Telegram user IDs allowed to run commands
DRY = "--dry" in sys.argv
ROLLOVER_HOUR = int(os.environ.get("ROLLOVER_HOUR", "6"))  # before this IST hour, "today" still means the previous study day
ALERT_CHAT_ID = os.environ.get("ALERT_CHAT_ID", "") or "7574436736"  # admin DM that gets failure alerts
BASE_H = 1080          # 16:9 canvas height; it only grows when there are too many rows to fit
MIN_ROW, MAX_ROW = 32, 84   # row height limits in px (zoom out / zoom in)
OVERHEAD = 317         # px of the canvas used by everything except the rows (calibrated)


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
body{margin:0;width:1920px;height:var(--H,1080px);padding:34px;background:var(--bg);color:var(--tx);
font-family:-apple-system,'SF Pro Display',Inter,'Helvetica Neue','Liberation Sans',Arial,sans-serif;
display:flex;flex-direction:column;gap:14px}
.wrap{flex:1;display:flex;gap:22px;min-height:0}
.panel{background:var(--card);border-radius:30px;padding:26px 30px 14px;display:flex;flex-direction:column;box-shadow:0 2px 24px rgba(0,0,0,.05)}
.pl{width:680px}.pr{flex:1}
.ph{display:flex;justify-content:space-between;align-items:flex-start}h1{margin:0;font-size:42px;letter-spacing:-1.1px}
.sub{font-size:17px;color:var(--mu);margin-top:3px}
.pill{background:var(--tx);color:var(--bg);border-radius:999px;padding:8px 16px;font-size:15px;font-weight:600;margin-top:6px}
.chips{display:flex;gap:10px;margin:14px 0 10px}
.chip{flex:1;min-width:0;background:var(--chip);border-radius:16px;padding:10px 14px;display:flex;align-items:center;font-size:19px}
.chip:first-child{background:var(--tx);color:var(--bg)}.cn{flex:1;min-width:0;font-weight:700;margin-left:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ct{margin-left:8px;flex:none;font-weight:800;font-variant-numeric:tabular-nums}
.bd{width:calc(26px*var(--f,1));height:calc(26px*var(--f,1));border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:calc(13px*var(--f,1));font-weight:700;background:var(--chip);color:var(--tx);flex:none;margin-right:4px}
.chip:first-child .bd{background:var(--bg);color:var(--tx)}
.b1{background:#fbbf24!important;color:#1d1d1f!important}.b2{background:#d1d5db!important;color:#1d1d1f!important}.b3{background:#e0a46b!important;color:#1d1d1f!important}
.th,.row{display:flex;align-items:center}
.th{font-size:13px;color:var(--mu);font-weight:600;height:40px;border-bottom:1px solid var(--ln)}
.th small,.dc small{display:block;font-weight:400;font-size:11px;opacity:.7}
.row{flex:none;height:var(--rh,42px);border-bottom:1px solid var(--ln);font-size:calc(18px*var(--f,1))}.row.sum{font-weight:800;border-bottom:none}
.nm{width:150px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:6px}.pr .nm{width:140px}
.dc{width:70px;text-align:center;flex:none;padding:2px 0}.dc.tdy{background:var(--tdy);border-radius:10px}.th .dc.tdy{color:#0a84ff;font-weight:700}
.c{display:inline-block;min-width:56px;padding:calc(3px*var(--f,1)) 0;border-radius:8px;font-weight:600;font-size:calc(16px*var(--f,1));font-variant-numeric:tabular-nums}
.c.g,.tm.g{background:var(--gb);color:var(--gt)}.c.a,.tm.a{background:var(--ab);color:var(--at)}.c.r,.tm.r{background:var(--rb);color:var(--rt)}
.z{color:var(--mu);opacity:.5;font-style:normal}.off{color:var(--mu);font-size:14px}
.tr{flex:1;height:10px;border-radius:5px;background:var(--tk);margin:0 16px;position:relative}.tr i{display:block;height:100%;border-radius:5px}
.fg{background:#34c759}.fa{background:#ff9f0a}.fr{background:#ff3b30}
.tm{width:80px;text-align:center;font-weight:700;border-radius:8px;padding:3px 0;font-variant-numeric:tabular-nums}
.tm.z{background:none}.row.sum .tm{background:none;color:var(--tx)}
.tot{width:190px;padding-left:14px;flex:none}.tot b{font-size:calc(19px*var(--f,1))}.tot em{font-style:normal;color:var(--mu);font-size:14px}
.pb{display:block;height:calc(6px*var(--f,1));background:var(--tk);border-radius:3px;margin-top:4px;overflow:hidden}.pb i{display:block;height:100%}
.sdone{background:#34c759}.son{background:#0a84ff}.srisk{background:#ff9f0a}.sno{background:#ff3b30}
.av{width:78px;text-align:center;flex:none;font-variant-numeric:tabular-nums}.stw{width:124px;text-align:center;flex:none}
.st{display:inline-block;min-width:104px;padding:calc(5px*var(--f,1)) 0;border-radius:8px;font-size:calc(13px*var(--f,1));font-weight:800;letter-spacing:.3px}
.st.done{background:var(--gb);color:var(--gt)}.st.on{background:var(--bb);color:var(--bt)}
.st.risk{background:var(--ab);color:var(--at)}.st.no{background:var(--rb);color:var(--rt)}
.legend{display:flex;justify-content:space-between;font-size:14px;color:var(--mu);padding:0 8px}"""


def layout(n_people):
    """Zoom rows in/out to fit the entries. 16:9 stays as long as rows fit; with many
    members (up to ~30) rows shrink to MIN_ROW and the canvas grows taller instead."""
    rows = n_people + 1                       # + group total row
    rh = max(MIN_ROW, min(MAX_ROW, (BASE_H - OVERHEAD) / rows))
    height = max(BASE_H, int(round(OVERHEAD + rh * rows)))
    f = max(0.8, min(1.0, rh / 42))
    return rh, f, height


def snapshot(people, today):
    """Show the board as it stood at the end of day `today` (0-based): hide later days, re-total."""
    for p in people:
        for d in range(today + 1, len(p["mins"])):
            p["mins"][d], p["raw"][d] = 0, ""
        p["total"] = sum(p["mins"])


def build_html(people, dates, n_days, today, now, stamp="Updated"):
    e = html.escape
    rh, f, height = layout(len(people))
    ttl = ("Today" if stamp == "Updated" else "Yesterday" if dates and dates[today] == now.date() - dt.timedelta(days=1)
           else dates[today].strftime("%d %b") if dates else "Snapshot")
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
    left = (f"<div class='panel pl'><div class='ph'><div><h1>{ttl}</h1><div class='sub'>{day_sub}</div></div>"
            f"<div class='pill'>{dstr(today, '%a, %d %b %Y')}</div></div>"
            f"<div class='chips'>{chips([(p['name'], fmt(p['mins'][today])) for p in day[:3]])}</div>"
            f"<div class='th'><span style='width:30px'></span><span style='width:150px'>Name</span>"
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
             f"<div class='sub'>Weekly target {WEEKLY_TARGET_H:g}h &middot; {stamp} {(dates[today] if dates else now).strftime('%d %b %Y') if stamp != 'Updated' else now.strftime('%d %b %Y')}</div></div>"
             f"<div class='pill'>{cycle}Day {elapsed} of {n_days}</div></div>"
             f"<div class='chips'>{chips([(p['name'], fmt(p['total'])) for p in wk[:3]])}</div>"
             f"<div class='th'><span style='width:30px'></span><span style='width:140px'>Name</span>{hd}"
             f"<span class='tot'>Weekly total</span><span class='av'>Avg/day</span><span class='stw'>Status</span></div>{rrows}</div>")

    legend = (f"<div class='legend'><span>Day cells: green = {DAILY_TARGET_H:g}h+ &middot; amber = {DAILY_TARGET_H / 2:g}&ndash;{DAILY_TARGET_H:g}h &middot; red = under {DAILY_TARGET_H / 2:g}h</span>"
              f"<span>DONE = {WEEKLY_TARGET_H:g}h &middot; ON TRACK = avg {ONTRACK_AVG_H:g}h+ &middot; AT RISK = avg {ATRISK_AVG_H:g}h+ &middot; UNLIKELY = below</span></div>")
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body><div class='wrap'>{left}{right}</div>{legend}</body></html>").replace(
        "<style>", f"<style>:root{{--rh:{rh:.1f}px;--f:{f:.3f};--H:{height}px}}", 1), height


# ---------- caption (Telegram HTML) ----------
def caption(people, today, now, day_date=None):
    e = html.escape
    now = day_date or now
    td = sorted(people, key=lambda p: -p["mins"][today])[:3]
    wk = sorted(people, key=lambda p: -p["total"])[:3]
    d = now.day
    suffix = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    date_s = f"{d}{suffix} {now.strftime('%B, %A')}"
    medals = ["🥇", "🥈", "🥉"]
    t = "\n".join(f"{medals[i]} #{i + 1} {e(p['name'])} - <b>{fmt(p['mins'][today])}</b>" for i, p in enumerate(td))
    w = "\n".join(f"{medals[i]} #{i + 1} {e(p['name'])} - <b>{fmt(p['total'])}</b>" for i, p in enumerate(wk))
    best = list(dict.fromkeys([td[0]["name"]] + [p["name"] for p in wk[:2]]))
    return (f"<b>{date_s}</b>. Y'all did great :)\n\n"
            f"<b>Top 3 Today</b>\n{t}\n\n"
            f"<b>Top 3 this week</b>\n{w}\n\n"
            f"<b>Highest chance of making it to the list in the group</b> = <b>{e(', '.join(best))}</b>")


def top3_caption(rows, head, cheer, what):
    """Caption for the weekly video / monthly board / monthly video: heading, top 3, then a random quote."""
    import quotes
    e = html.escape
    medals = ["🥇", "🥈", "🥉"]
    lines = "\n".join(f"{medals[i]} #{i + 1} {e(r['name'])} - <b>{fmt(r['total'])}</b>" for i, r in enumerate(rows[:3]))
    return f"{head}\n{cheer}\n\n<b>Top 3 {what}</b>\n{lines}\n\n{quotes.block()}"


# ---------- helpers ----------
def now_ist():
    return dt.datetime.now(ZoneInfo("Asia/Kolkata"))


def board_date(now=None):
    """Date the automatic board is for. A run (or rerun) that lands after midnight, before ROLLOVER_HOUR,
    still belongs to the previous day, e.g. the 11:45 PM run that was delayed or re-run at 12:30 AM."""
    now = now or now_ist()
    return now.date() - dt.timedelta(days=1) if now.hour < ROLLOVER_HOUR else now.date()


def tg(method, **kw):
    t0 = time.time()
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=60, **kw)
    print(f"{method} -> {r.status_code} in {time.time() - t0:.1f}s: {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def target(chat=None):
    """Group topic by default; a DM chat id when given."""
    return {"chat_id": chat} if chat else {"chat_id": CHAT_ID, "message_thread_id": THREAD_ID}


POSTED = [0]   # counts posts that reached Telegram, so a retry never repeats something already sent


def send_photo(png, cap, chat=None):
    with open(png, "rb") as f:
        tg("sendPhoto", data={**target(chat), "caption": cap, "parse_mode": "HTML"}, files={"photo": f})
    POSTED[0] += 1


def send_video(mp4, cap, chat=None, seconds=15):
    with open(mp4, "rb") as f:
        tg("sendVideo", data={**target(chat), "caption": cap, "parse_mode": "HTML", "supports_streaming": "true",
                              "width": 1920, "height": 1080, "duration": int(seconds)}, files={"video": f})
    POSTED[0] += 1


def dm(chat, text, markup=None):
    import json
    d = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
    if markup:
        d["reply_markup"] = json.dumps(markup)
    tg("sendMessage", data=d)


def shoot(page_html, width, height, png):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        pg = b.new_page(viewport={"width": width, "height": height}, device_scale_factor=1.25)
        pg.set_content(page_html)
        pg.screenshot(path=png, full_page=True)
        b.close()


def cycle_info(on_date=None):
    """Sheet data + the real calendar dates of the cycle. If the sheet has no 'Cycle start' cell,
    cycles are assumed to run Monday to Sunday and the dates are derived from the board date."""
    people, dates, n_days = parse(fetch_rows())
    d = on_date or board_date()
    if not dates:
        start = d - dt.timedelta(days=d.weekday())
        dates = [start + dt.timedelta(days=i) for i in range(n_days)]
    return people, dates, n_days, d


# ---------- daily board ----------
def render(on_date=None, png="leaderboard.png"):
    """Board for a calendar date (default: board_date()). Returns (caption, error)."""
    now = now_ist()
    people, dates, n_days, d = cycle_info(on_date)
    today = int(DAY_OVERRIDE) - 1 if DAY_OVERRIDE else (d - dates[0]).days
    if today < 0 or today >= n_days:
        return None, f"{d.isoformat()} is outside the current cycle ({dates[0]} to {dates[-1]})."
    snapshot(people, today)  # board exactly as it stood at the end of that day
    stamp = "Updated" if (dates and dates[today] == now.date()) else "Snapshot"
    page_html, height = build_html(people, dates, n_days, today, now, stamp)
    shoot(page_html, 1920, height, png)
    cap = caption(people, today, now, dates[today] if dates else None)
    print(f"{len(people)} members, canvas 1920x{height}")
    return cap, None


# ---------- weekly archive, videos, monthly ----------
def week_state(on_date=None):
    people, dates, n_days, d = cycle_info(on_date)
    last = max(0, min(n_days - 1, (d - dates[0]).days))
    return people, dates, n_days, last


def video_for(ranked, title, subtitle, kicker, out, label="THE REST OF THE BOARD"):
    import podium
    return podium.make_video(out, title, subtitle, kicker, ranked, label)


def weekly_video(ranked, title, subtitle, kicker, out):
    import podium_weekly
    return podium_weekly.make_weekly_video(out, title, subtitle, kicker, ranked)


def period_post(weeks, k, chat=None, specimen=False, tag=""):
    """Board image + podium video for the last k weeks."""
    import periods
    rows = periods.aggregate(weeks)
    title, span, labels = periods.period_names(k, weeks)
    page, h = periods.board_html(title, span, rows, labels, specimen)
    png = f"period_{k}.png"
    shoot(page, 1700, 400, png)  # short viewport + full_page: image is exactly as tall as the content
    spec = " · <i>specimen</i>" if specimen else ""
    send_photo(png, top3_caption(rows, f"<b>{html.escape(title)}</b> · {span}{spec}", "Y'all did great :)", "this month") + tag, chat)
    mp4 = f"period_{k}.mp4"
    secs = video_for([(r["name"], r["total"]) for r in rows], title, span, ("SPECIMEN · " if specimen else "") + "MONTHLY PODIUM", mp4)
    send_video(mp4, top3_caption(rows, f"<b>{html.escape(title)}</b> podium · {span}{spec}", "Here's the month in one clip :)", "this month"), chat, secs)


def weekly_run(force=False, on_date=None):
    """Archive the finished cycle + post its podium video. Returns a status line for the admin."""
    import periods
    people, dates, n_days, last = week_state(on_date)
    if last != n_days - 1 and not force:
        return f"This cycle is only on day {last + 1} of {n_days}, so it is not finished. Send <code>/weekly force</code> to run it anyway."
    wk = periods.week_dict(people, dates, n_days, last)
    path = periods.save_week(wk)
    n = len(periods.load_weeks())
    print("archived", path, f"({n} weeks stored)")
    rows = periods.aggregate([wk])
    rng = f"{dates[0].strftime('%d %b')} – {dates[-1].strftime('%d %b %Y')}"
    secs = weekly_video([(r["name"], r["total"]) for r in rows], f"Week {n}", f"{rng} · weekly total", "WEEKLY PODIUM", "weekly.mp4")
    if not DRY:
        send_video("weekly.mp4", top3_caption(rows, f"<b>Week {n} podium</b> · {rng}", "Y'all did great :)", "this week"), None, secs)
    return f"Weekly podium for {rng} posted. Week {n} is saved in data/weeks."


def monthly_run(on_date=None):
    """Monthly board + podium video from the last 4 archived weeks (fewer if that is all there is)."""
    import periods
    weeks = periods.load_weeks()[-4:]
    if not weeks:
        return "No weeks are archived yet. Run /weekly at the end of a cycle first."
    period_post(weeks, len(weeks))
    return f"Monthly leaderboard posted ({len(weeks)} week{'s' if len(weeks) > 1 else ''}: {weeks[0]['cycle_start']} onwards)."


def specimen(chat):
    """/show: preview of the weekly and monthly boards and videos, sent to the admin's chat."""
    import periods
    people, dates, n_days, last = week_state()
    live = periods.week_dict(people, dates, n_days, last)
    archived = [w for w in periods.load_weeks() if w["cycle_start"] != live["cycle_start"]]
    dm(chat, "Preparing specimens: the weekly video, then the monthly leaderboard and video. This takes a few minutes.")
    rows = periods.aggregate([live])
    secs = weekly_video([(r["name"], r["total"]) for r in rows], "Weekly podium",
                     f"{dates[0].strftime('%d %b')} – {dates[-1].strftime('%d %b %Y')} · weekly total", "SPECIMEN · WEEKLY PODIUM", "weekly.mp4")
    send_video("weekly.mp4", top3_caption(rows, "<b>Weekly podium</b> · <i>specimen</i> · "
               f"{dates[0].strftime('%d %b')} – {dates[-1].strftime('%d %b %Y')}", "Y'all did great :)", "this week"), chat, secs)
    period_post(periods.specimen_weeks(archived, live, 4), 4, chat, specimen=True)
    dm(chat, "Done. Weeks with no saved history yet are padded with copies of the latest week for these specimens.")


# ---------- admin commands (polled from Telegram) ----------
GROUP_CMDS = {"/daily": "today", "/today": "today", "/leaderboard": "today", "/rerun": "today", "/yesterday": "yesterday",
              "/weekly": "weekly", "/monthly": "monthly", "/show": "show"}


MENU = [("daily", "Post today's leaderboard to the group"), ("yesterday", "Post yesterday's leaderboard to the group"),
        ("weekly", "Save the finished week and post the weekly podium video"),
        ("monthly", "Post the monthly leaderboard and video"),
        ("show", "Send specimen weekly video and monthly board + video to my DM")]


def set_menu():
    """Command menu visible only in the admins' own chats (nobody else sees or can use it)."""
    import json
    for uid in ADMIN_IDS:
        try:
            tg("setMyCommands", data={"commands": json.dumps([{"command": c, "description": d} for c, d in MENU]),
                                      "scope": json.dumps({"type": "chat", "chat_id": uid})})
        except Exception as ex:  # e.g. admin has not started the bot yet
            print("menu not set for", uid, ex)


def actions_from_updates(upd):
    """Turn Telegram updates into actions. Only admins are honoured; everyone else is ignored."""
    actions = []
    print(f"{len(upd)} update(s); admins = {sorted(ADMIN_IDS)}")
    for u in upd:
        m = u.get("message") or {}
        cq = u.get("callback_query") or {}
        print("  update", u.get("update_id"), "from", (m.get("from") or cq.get("from") or {}).get("id"),
              "chat", (m.get("chat") or {}).get("id"), "text", repr((m.get("text") or cq.get("data") or "")[:30]))

    def add(a):
        if a not in actions:
            actions.append(a)

    for u in upd:
        cq = u.get("callback_query")
        if cq:
            if (cq.get("from") or {}).get("id") in ADMIN_IDS and (cq.get("data") or "").startswith("rr:"):
                _, mode, d = cq["data"].split(":", 2)
                add({"do": "rerun", "mode": mode, "date": d, "chat": cq["message"]["chat"]["id"]})
            continue
        m = u.get("message") or {}
        if (m.get("from") or {}).get("id") not in ADMIN_IDS:
            continue
        words = (m.get("text") or "").split()
        cmd = words[0].split("@")[0].lower() if words else ""
        if cmd in GROUP_CMDS:
            add({"do": GROUP_CMDS[cmd], "chat": m["chat"]["id"], "force": "force" in [w.lower() for w in words[1:]]})
    return actions


def save_actions(actions):
    import json
    with open("actions.json", "w") as f:
        json.dump(actions, f)
    print("actions:", actions or "(none)")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"has={'true' if actions else 'false'}\n")


def poll():
    """Fallback without a webhook: read pending updates with getUpdates, acknowledge them."""
    import json
    set_menu()
    try:
        upd = tg("getUpdates", data={"timeout": 0, "allowed_updates": json.dumps(["message", "callback_query"])})["result"]
    except requests.HTTPError as ex:
        if ex.response is not None and ex.response.status_code == 409:
            print("A webhook is set, so getUpdates is off; commands arrive through the webhook instead.")
            return save_actions([])
        raise
    for u in upd:
        cq = u.get("callback_query")
        if cq and (cq.get("from") or {}).get("id") in ADMIN_IDS:
            tg("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": "Re-running, result in a few minutes"})
    actions = actions_from_updates(upd)
    if upd:
        tg("getUpdates", data={"offset": upd[-1]["update_id"] + 1, "timeout": 0})
    save_actions(actions)


def from_webhook():
    """Webhook path: the Worker forwards one Telegram update as UPDATE_JSON."""
    import json
    set_menu()
    raw = os.environ.get("UPDATE_JSON", "").strip()
    upd = json.loads(raw) if raw and raw != "null" else None
    save_actions(actions_from_updates([upd] if upd else []))


def run_board(on_date, chat_for_reply=None, label=""):
    cap, err = render(on_date)
    if err:
        if chat_for_reply:
            dm(chat_for_reply, err)
        print(err)
        return
    send_photo("leaderboard.png", cap)
    if chat_for_reply:
        dm(chat_for_reply, f"Posted {label or 'the leaderboard'} to the group.")


def run_action(a, chat):
    if a["do"] == "today":
        run_board(None, chat, "today's leaderboard")
    elif a["do"] == "yesterday":
        run_board(board_date() - dt.timedelta(days=1), chat, "yesterday's leaderboard")
    elif a["do"] == "weekly":
        dm(chat, weekly_run(force=a.get("force")))
    elif a["do"] == "monthly":
        dm(chat, monthly_run())
    elif a["do"] == "show":
        specimen(chat)
    elif a["do"] == "rerun":
        d = dt.date.fromisoformat(a["date"])
        if a["mode"] == "weekly":
            dm(chat, weekly_run(force=True, on_date=d))
        elif a["mode"] == "monthly":
            dm(chat, monthly_run())
        else:
            run_board(d, chat, f"the {d.strftime('%d %b')} leaderboard")


RETRY_WAITS = [45, 120]   # seconds before the 2nd and 3rd attempt


def process():
    import json
    for a in json.load(open("actions.json")):
        chat = a.get("chat") or ALERT_CHAT_ID
        for attempt in range(len(RETRY_WAITS) + 1):
            before = POSTED[0]
            try:
                run_action(a, chat)
                break
            except Exception as ex:
                print(f"action failed (attempt {attempt + 1}):", a, ex)
                # retry only while nothing has been posted yet, so a half-finished run is never duplicated
                if attempt < len(RETRY_WAITS) and POSTED[0] == before and a["do"] != "show":
                    time.sleep(RETRY_WAITS[attempt])
                    continue
                bd = board_date()   # tell the admin, with a Rerun button that remembers the exact day
                cb = {"today": f"rr:day:{bd}", "yesterday": f"rr:day:{bd - dt.timedelta(days=1)}",
                      "weekly": f"rr:weekly:{bd}", "monthly": f"rr:monthly:{bd}"}.get(a["do"])
                dm(chat, f"<code>/{html.escape(a['do'])}</code> failed after {attempt + 1} attempt(s): {html.escape(str(ex))[:300]}",
                   [[{"text": "🔁 Rerun", "callback_data": cb}]] if cb else None)
                break


def main():
    if "--poll" in sys.argv:
        return poll()
    if "--update" in sys.argv:
        return from_webhook()
    if "--process" in sys.argv:
        return process()
    if "--weekly" in sys.argv:
        return print(weekly_run(force="--force" in sys.argv))
    if "--monthly" in sys.argv:
        return print(monthly_run())
    on_date = board_date() - dt.timedelta(days=1) if "--yesterday" in sys.argv else None
    cap, err = render(on_date)
    if err:
        print(err)
        return
    print(cap)
    if not DRY:
        send_photo("leaderboard.png", cap)


if __name__ == "__main__":
    main()
