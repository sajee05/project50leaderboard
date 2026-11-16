"""Weekly archive + monthly (4-week) boards.
Each finished cycle is saved as data/weeks/<cycle-start>.json (committed by the workflow, so it is free
and survives sheet resets). Longer boards are computed from those files."""
import glob, html, json, os
import datetime as dt

DATA_DIR = os.environ.get("DATA_DIR", "data/weeks")
DAILY_H = float(os.environ.get("DAILY_TARGET_H", "8"))
WEEKLY_H = float(os.environ.get("WEEKLY_TARGET_H", "50"))
ON_H = float(os.environ.get("ONTRACK_AVG_H", "8"))
RISK_H = float(os.environ.get("ATRISK_AVG_H", "7"))


def fmt(m):
    m = int(round(m))
    return f"{m // 60}:{m % 60:02d}"


# ---------- archive ----------
def week_dict(people, dates, n_days, last_day):
    """A cycle as it stands at the end of 0-based day `last_day`."""
    return {"cycle_start": dates[0].isoformat() if dates else "", "n_days": n_days, "elapsed": last_day + 1,
            "people": [{"name": p["name"], "mins": list(p["mins"][:last_day + 1]) + [0] * (n_days - last_day - 1)}
                       for p in people]}


def save_week(week, directory=DATA_DIR):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{week['cycle_start']}.json")
    with open(path, "w") as f:
        json.dump(week, f, indent=1)
    return path


def load_weeks(directory=DATA_DIR):
    out = []
    for p in sorted(glob.glob(os.path.join(directory, "*.json"))):
        with open(p) as f:
            out.append(json.load(f))
    return sorted(out, key=lambda w: w["cycle_start"])


def specimen_weeks(archived, live, k):
    """Last k weeks for a preview: archived weeks + the live cycle; padded with copies if history is short."""
    weeks = (archived + [live])[-k:]
    while len(weeks) < k:
        weeks.insert(0, weeks[0])
    return weeks


# ---------- aggregate ----------
def aggregate(weeks):
    rows = {}
    for wi, w in enumerate(weeks):
        for p in w["people"]:
            key = p["name"].strip().lower()
            r = rows.setdefault(key, {"name": p["name"], "weekly": [0] * len(weeks), "days": []})
            r["name"] = p["name"]
            r["weekly"][wi] = sum(p["mins"])
            r["days"] += p["mins"][:w.get("elapsed", w["n_days"])]
    out = []
    for r in rows.values():
        d = r["days"]
        r["total"] = sum(r["weekly"])
        r["avg"] = r["total"] / max(1, len(d))
        r["good"] = sum(1 for x in d if x >= DAILY_H * 60)
        r["ndays"] = len(d)
        r["best"] = max(d) if d else 0
        out.append(r)
    out.sort(key=lambda r: -r["total"])
    return out


def status_of(total, avg, k):
    if total >= WEEKLY_H * 60 * k:
        return "DONE", "done"
    if avg >= ON_H * 60:
        return "ON TRACK", "on"
    if avg >= RISK_H * 60:
        return "AT RISK", "risk"
    return "UNLIKELY", "no"


# ---------- board image ----------
CSS = """*{box-sizing:border-box}
:root{--bg:#f5f5f7;--card:#fff;--tx:#1d1d1f;--mu:#86868b;--chip:#f2f2f5;--ln:#efeff2;--tk:#ececf0;
--gb:rgba(52,199,89,.16);--gt:#17803a;--ab:rgba(255,159,10,.18);--at:#b25e00;--rb:rgba(255,59,48,.13);--rt:#c4271c;
--bb:rgba(10,132,255,.13);--bt:#0a63c9}
body{margin:0;width:1700px;padding:34px;background:var(--bg);color:var(--tx);
font-family:-apple-system,'SF Pro Display',Inter,'Helvetica Neue','Liberation Sans',Arial,sans-serif}
.panel{background:var(--card);border-radius:30px;padding:28px 34px 16px;box-shadow:0 2px 24px rgba(0,0,0,.05)}
.ph{display:flex;justify-content:space-between;align-items:flex-start}h1{margin:0;font-size:46px;letter-spacing:-1.2px}
.sub{font-size:18px;color:var(--mu);margin-top:4px}
.pill{background:var(--tx);color:var(--bg);border-radius:999px;padding:9px 18px;font-size:15px;font-weight:700;margin-top:6px;letter-spacing:.4px}
.pill.sp{background:#ff9f0a;color:#fff;margin-left:8px}
.th,.row{display:flex;align-items:center}
.th{font-size:13px;color:var(--mu);font-weight:600;height:44px;margin-top:14px;border-bottom:1px solid var(--ln)}
.row{border-bottom:1px solid var(--ln);height:var(--rh);font-size:calc(19px*var(--f))}.row.sum{font-weight:800;border-bottom:none}
.bd{width:calc(28px*var(--f));height:calc(28px*var(--f));border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
font-size:calc(13px*var(--f));font-weight:700;background:var(--chip);flex:none;margin-right:8px}
.b1{background:#fbbf24}.b2{background:#d1d5db}.b3{background:#e0a46b}
.nm{flex:1;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:8px}
.wk{width:104px;text-align:center;flex:none}
.c{display:inline-block;min-width:82px;padding:calc(3px*var(--f)) 0;border-radius:8px;font-weight:600;font-size:calc(16px*var(--f));font-variant-numeric:tabular-nums}
.g{background:var(--gb);color:var(--gt)}.a{background:var(--ab);color:var(--at)}.r{background:var(--rb);color:var(--rt)}
.tot{width:250px;padding-left:12px;flex:none}.tot b{font-size:calc(21px*var(--f))}.tot em{font-style:normal;color:var(--mu);font-size:14px}
.pb{display:block;height:calc(6px*var(--f));background:var(--tk);border-radius:3px;margin-top:3px;overflow:hidden}.pb i{display:block;height:100%}
.sdone{background:#34c759}.son{background:#0a84ff}.srisk{background:#ff9f0a}.sno{background:#ff3b30}
.n{width:96px;text-align:center;flex:none;font-variant-numeric:tabular-nums}.stw{width:138px;text-align:center;flex:none}
.st{display:inline-block;min-width:108px;padding:calc(5px*var(--f)) 0;border-radius:8px;font-size:calc(13px*var(--f));font-weight:800;letter-spacing:.3px}
.st.done{background:var(--gb);color:var(--gt)}.st.on{background:var(--bb);color:var(--bt)}.st.risk{background:var(--ab);color:var(--at)}.st.no{background:var(--rb);color:var(--rt)}
.legend{margin-top:12px;font-size:14px;color:var(--mu);padding:0 8px}"""


def board_html(title, subtitle, rows, week_labels, specimen=False):
    e = html.escape
    k = len(week_labels)
    n = len(rows)
    rh = max(34, min(54, 860 / (n + 1)))
    f = max(0.78, min(1.0, rh / 48))
    height = int(34 * 2 + 28 + 16 + 120 + 60 + rh * (n + 1) + 50)
    cls = lambda x, tgt: "g" if x >= tgt else "a" if x >= tgt / 2 else "r"
    hd = "".join(f"<span class='wk'>{e(l)}</span>" for l in week_labels)
    body = ""
    for i, r in enumerate(rows, 1):
        wk = "".join(f"<span class='wk'><b class='c {cls(x, WEEKLY_H * 60)}'>{fmt(x)}</b></span>" if x else
                     "<span class='wk' style='color:#c7c7cc'>&ndash;</span>" for x in r["weekly"])
        st, sc = status_of(r["total"], r["avg"], k)
        pct = min(100, r["total"] / (WEEKLY_H * 60 * k) * 100)
        body += (f"<div class='row'><span class='bd b{i if i <= 3 else 0}'>{i}</span><span class='nm'>{e(r['name'])}</span>{wk}"
                 f"<span class='tot'><b>{fmt(r['total'])}</b><em> / {WEEKLY_H * k:g}h</em><span class='pb'><i class='s{sc}' style='width:{pct:.1f}%'></i></span></span>"
                 f"<span class='n'>{fmt(r['avg'])}</span><span class='n'>{r['good']}/{r['ndays']}</span>"
                 f"<span class='n'>{fmt(r['best'])}</span><span class='stw'><b class='st {sc}'>{st}</b></span></div>")
    gt = "".join(f"<span class='wk'>{fmt(sum(r['weekly'][j] for r in rows))}</span>" for j in range(k))
    body += (f"<div class='row sum'><span class='bd' style='background:none'></span><span class='nm'>Group total</span>{gt}"
             f"<span class='tot'><b>{fmt(sum(r['total'] for r in rows))}</b></span><span class='n'></span><span class='n'></span><span class='n'></span><span class='stw'></span></div>")
    sp = "<span class='pill sp'>SPECIMEN</span>" if specimen else ""
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>:root{{--rh:{rh:.1f}px;--f:{f:.3f}}}{CSS}</style></head><body>"
            f"<div class='panel'><div class='ph'><div><h1>{e(title)}</h1><div class='sub'>{e(subtitle)}</div></div>"
            f"<div style='display:flex'><div class='pill'>{k} week{'s' if k > 1 else ''} &middot; {n} members</div>{sp}</div></div>"
            f"<div class='th'><span style='width:36px'></span><span class='nm'>Name</span>{hd}<span class='tot'>Total</span>"
            f"<span class='n'>Avg/day</span><span class='n'>Days {DAILY_H:g}h+</span><span class='n'>Best day</span><span class='stw'>Status</span></div>{body}"
            f"<div class='legend'>Week cells: green = {WEEKLY_H:g}h+ &middot; amber = half or more &middot; red = under half &middot; "
            f"DONE = {WEEKLY_H:g}h per week &middot; ON TRACK = avg {ON_H:g}h+ &middot; AT RISK = avg {RISK_H:g}h+</div></div></body></html>")
    return page, height + 40


def period_names(k, weeks):
    first = dt.date.fromisoformat(weeks[0]["cycle_start"])
    last = dt.date.fromisoformat(weeks[-1]["cycle_start"]) + dt.timedelta(days=weeks[-1]["n_days"] - 1)
    span = f"{first.strftime('%d %b')} – {last.strftime('%d %b %Y')}"
    title = "Monthly leaderboard"
    labels = [f"Wk {dt.date.fromisoformat(w['cycle_start']).strftime('%d %b')}" for w in weeks]
    return title, span, labels
