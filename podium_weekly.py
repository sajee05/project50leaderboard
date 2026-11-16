"""Weekly video: a 12 s countdown (last place up to first) with the podium rising for the final three.
Always exactly TOTAL seconds so it fits the weekly music track, whether there are 5 or 30 members.
Timing lives in one place (timeline) and drives both the animation and the sound effects."""
import json, os, glob
import podium

TOTAL = 12.0


def timeline(n):
    """Reveal times. Ranks n..4 count down between the drop (2.5 s) and 6.6 s, then 3rd / 2nd / 1st on the beat lifts."""
    r = max(0, n - 3)
    inter = min(0.4, 4.1 / r) if r else 0.0
    start = 6.6 - r * inter
    return {"total": TOTAL, "p3": 6.9, "p2": 8.0, "p1": 9.75, "inter": inter,
            "rows": {str(rank): round(start + (n - rank) * inter, 3) for rank in range(4, n + 1)}}


PAGE = r"""<!doctype html><html><head><meta charset='utf-8'><style>*{box-sizing:border-box;margin:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#07080d;color:#f5f5f7;
font-family:Inter,-apple-system,'SF Pro Display','Helvetica Neue','Liberation Sans',Arial,sans-serif}
#bg{position:absolute;inset:0;background:
radial-gradient(900px 700px at 28% 70%,rgba(70,90,255,.22),transparent 70%),
radial-gradient(800px 600px at 85% 15%,rgba(255,170,60,.13),transparent 70%),
linear-gradient(160deg,#0b0d18,#06070b)}
canvas{position:absolute;inset:0}
.abs{position:absolute}
#head{left:0;top:0;transform-origin:0 0;width:900px}
#kick{font-size:22px;letter-spacing:7px;font-weight:700;color:#8b93ff}
#ttl{font-size:84px;font-weight:800;letter-spacing:-2.5px;line-height:1.1;margin-top:4px}
#sub{display:inline-block;margin-top:10px;font-size:32px;font-weight:700;color:#fff;background:rgba(139,147,255,.18);border:1px solid rgba(139,147,255,.35);border-radius:999px;padding:8px 26px}
#panel{background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.09);border-radius:34px;padding:24px 26px}
#grid{display:flex;gap:30px}
.col{flex:1;min-width:0}
.rw{display:flex;align-items:center;gap:12px;border-bottom:1px solid rgba(255,255,255,.07);margin-bottom:var(--gap)}
.rw.top .rk{color:#ffd45e}
.rk{width:2.2em;font-weight:800;color:#8b93ff;font-variant-numeric:tabular-nums}
.rn{width:30%;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{flex:1;height:6px;border-radius:3px;background:rgba(255,255,255,.1);overflow:hidden}
.bar i{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,#6b78ff,#9be7ff)}
.rv{font-weight:800;font-variant-numeric:tabular-nums;min-width:3.3em;text-align:right}
.pil{border-radius:30px 30px 0 0;overflow:hidden;display:flex;justify-content:center;box-shadow:0 0 60px rgba(0,0,0,.4) inset}
.pil b{font-size:130px;font-weight:800;margin-top:14px;opacity:.9;color:rgba(10,10,20,.78)}
.g1{background:linear-gradient(180deg,#ffd45e,#c98a10)}
.g2{background:linear-gradient(180deg,#e9edf3,#8e97a6)}
.g3{background:linear-gradient(180deg,#f0b27a,#a8642d)}
.card{text-align:center}
.av{border-radius:50%;margin:0 auto 10px;display:flex;align-items:center;justify-content:center;font-weight:800;color:#0b0c14}
.nm{font-weight:800;letter-spacing:-.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vl{font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-1px}
.hl{font-size:20px;color:#9a9aa8;letter-spacing:3px;margin-top:2px}
#fade{background:#07080d;opacity:0;inset:0}
</style></head><body>
<div id='bg'></div><canvas id='cv' width='1920' height='1080'></canvas>
<div id='head' class='abs'><div id='kick'></div><div id='ttl'></div><div id='sub'></div></div>
<div id='panel' class='abs'></div><div id='stage'></div>
<div id='fade' class='abs'></div>
<script>
const D=__DATA__, TL=D.tl, R=D.ranked, n=R.length, ctx=document.getElementById('cv').getContext('2d');
const $=id=>document.getElementById(id), clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const eo=x=>1-Math.pow(1-clamp(x),3), eb=x=>{x=clamp(x);const c=1.7;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2)};
const fmt=m=>{m=Math.round(m);return Math.floor(m/60)+':'+String(m%60).padStart(2,'0')};
const rnd=i=>{const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)};
$('kick').textContent=D.kicker; $('ttl').textContent=D.title; $('sub').textContent=D.subtitle;
const maxv=Math.max(1,...R.map(p=>p.mins));

// ---- list (all members; revealed from the last place up to first) ----
const cols=n>14?2:1, per=Math.ceil(n/cols), PW=cols==2?1000:960, PX=70, PY=330, PH=690;
const inner=PH-64, gap=cols==2?6:8, rh=Math.min(70,Math.floor(inner/per)-gap), fs=Math.max(15,Math.min(30,Math.round(rh*.46)));
const panel=$('panel'); panel.style.cssText+=`left:${PX}px;top:${PY}px;width:${PW}px;height:${PH}px;--gap:${gap}px`;
let h='<div id="grid">';
for(let c=0;c<cols;c++){h+='<div class="col">';
  for(let i=c*per;i<Math.min(n,(c+1)*per);i++){const rank=i+1;
    h+=`<div class="rw ${rank<=3?'top':''}" id="r${rank}" style="height:${rh}px;font-size:${fs}px;opacity:0"><span class="rk">${rank}</span><span class="rn"></span><span class="bar"><i style="width:0%"></i></span><span class="rv"></span></div>`}
  h+='</div>'}
panel.innerHTML=h+'</div>';
R.forEach((p,i)=>{const e=$('r'+(i+1)); e.querySelector('.rn').textContent=p.name; e.dataset.v=p.mins});
const rowT=rank=>rank>3?TL.rows[String(rank)]:(rank==3?TL.p3:rank==2?TL.p2:TL.p1)+0.35;

// ---- podium (right): three wooden crates under the bar lamps ----
const cx=1480,pw=220,pg=18,base=1005, hts={1:380,2:290,3:215};
const slot={2:cx-(pw+pg),1:cx,3:cx+(pw+pg)}, tm={3:TL.p3,2:TL.p2,1:TL.p1};
const stage=$('stage'), els={};
for(const rank of [1,2,3]){const p=R[rank-1]; if(!p) continue; const x=slot[rank];
  const pil=document.createElement('div'); pil.className='abs pil g'+rank; pil.style.cssText+=`left:${x-pw/2}px;width:${pw}px`; pil.innerHTML='<b>'+rank+'</b>'; stage.appendChild(pil);
  const card=document.createElement('div'); card.className='abs card'; card.style.cssText+=`left:${x-pw/2-20}px;width:${pw+40}px`;
  const av=rank==1?104:88, init=(p.name.trim()[0]||'?').toUpperCase();
  card.innerHTML=`<div class='av g${rank}' style='width:${av}px;height:${av}px;font-size:${av*.46}px'>${init}</div><div class='nm' style='font-size:${rank==1?40:34}px'></div><div class='vl' style='font-size:${rank==1?58:48}px'></div><div class='hl'>HOURS</div>`;
  card.querySelector('.nm').textContent=p.name; stage.appendChild(card);
  els[rank]={pil,card,v:p.mins,vl:card.querySelector('.vl')}}

function render(t){
  ctx.clearRect(0,0,1920,1080);
  for(let i=0;i<70;i++){const x=(rnd(i)*1920+t*(8+rnd(i+9)*14))%1920,y=(rnd(i+3)*1080-t*(6+rnd(i+5)*10)+3240)%1080;
    ctx.globalAlpha=.10+.25*rnd(i+7);ctx.fillStyle='#cfd6ff';ctx.beginPath();ctx.arc(x,y,1+rnd(i+8)*2.2,0,7);ctx.fill()}
  ctx.globalAlpha=1;
  // title: fades in at the centre, then slides to the corner
  const flick=1;
  const k=eo((t-1.6)/.9), s=1.55-.55*k, px=420*(1-k)+80*k, py=330*(1-k)+60*k, op=eo((t-.15)/.5)*flick;
  const hd=$('head'); hd.style.opacity=op; hd.style.transform=`translate(${px}px,${py}px) scale(${s})`;
  const pa=eo((t-2.3)/.6); panel.style.opacity=pa; panel.style.transform=`translateX(${(1-pa)*-80}px)`;

  for(let rank=n;rank>=1;rank--){const e=$('r'+rank), rt=rowT(rank), q=eo((t-rt)/.45);
    e.style.opacity=q; e.style.transform=`translateX(${(1-q)*-70}px)`;
    e.querySelector('.bar i').style.width=(q*(+e.dataset.v/maxv)*100)+'%';
    e.querySelector('.rv').textContent=q>0?fmt(+e.dataset.v*eo((t-rt)/.7)):''}

  for(const rank of [1,2,3]){const e=els[rank]; if(!e) continue; const s0=tm[rank], p=clamp((t-s0)/.9), hh=hts[rank]*eo(p);
    e.pil.style.height=hh+'px'; e.pil.style.top=(base-hh)+'px'; e.pil.style.opacity=p>0?1:0;
    const cp=eb((t-s0-.45)/.6), cardH=rank==1?262:232;
    e.card.style.opacity=clamp((t-s0-.4)/.3); e.card.style.top=(base-hh-cardH-(1-clamp(cp))*36)+'px';
    e.vl.textContent=fmt(e.v*eo((t-s0-.5)/1.1))}
  $('fade').style.opacity=clamp((t-(TL.total-.6))/.6);
}
window.render=render;
</script></body></html>"""


# ---------- sound effects (synthesised; the weekly music track is layered underneath) ----------
def make_sfx(path, tl, n, rate=44100):
    import array, math, random, wave
    total = tl["total"]
    N = int(total * rate)
    L = [0.0] * N
    rnd = random.Random(11)

    def add(t0, dur, fn, gain):
        i0 = int(t0 * rate)
        for k in range(int(dur * rate)):
            i = i0 + k
            if 0 <= i < N:
                L[i] += fn(k / rate) * gain

    tick = lambda f: (lambda t: math.sin(6.283 * f * t) * math.exp(-t * 90) + .3 * (rnd.random() * 2 - 1) * math.exp(-t * 200))
    ding = lambda f: (lambda t: (math.sin(6.283 * f * t) + .5 * math.sin(6.283 * f * 2.76 * t) + .25 * math.sin(6.283 * f * 5.4 * t))
                      * math.exp(-t * 3.2) * min(1, t * 500))
    boom = lambda t: math.sin(6.283 * (34 + 70 * math.exp(-t * 8)) * t) * math.exp(-t * 2.6)
    swell = lambda d: (lambda t: (rnd.random() * 2 - 1) * (min(1, t / d) ** 2) * (1 if t < d else 0))
    pop = lambda t: (rnd.random() * 2 - 1) * math.exp(-t * 28)
    star = lambda f: (lambda t: math.sin(6.283 * f * t) * math.exp(-t * 7) * min(1, t * 600))

    add(0.15, 0.7, swell(0.7), 0.16)                    # title whoosh
    add(1.7, 0.8, swell(0.8), 0.16)                     # glide to the corner
    rows = sorted(tl["rows"].items(), key=lambda kv: kv[1])
    for j, (_, rt) in enumerate(rows):                  # countdown ticks, pitch climbing
        add(rt, 0.08, tick(620 + 900 * j / max(1, len(rows) - 1)), 0.20)
    for key, f, g in (("p3", 659.25, .6), ("p2", 783.99, .7)):
        add(tl[key] - 0.45, 0.45, swell(0.45), 0.18)
        add(tl[key], 1.0, boom, g)
        add(tl[key], 1.3, ding(f), 0.30)
    add(tl["p1"] - 0.45, 0.45, swell(0.45), 0.18)       # 1st place: same gentle treatment as 2nd and 3rd
    add(tl["p1"], 1.0, boom, 0.7)
    add(tl["p1"], 1.3, ding(880.0), 0.30)
    peak = max(abs(x) for x in L) or 1
    out = array.array("h", (int(max(-1, min(1, x / peak * 0.9)) * 32767) for x in L))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())


def audio(workdir, tl, n):
    fx = os.path.join(workdir, "weekly_sfx.wav")
    make_sfx(fx, tl, n)
    mine = os.environ.get("WEEKLY_MUSIC_FILE") or next(iter(sorted(glob.glob("assets/weekly.*"))), "")
    if mine and os.path.exists(mine):
        T = tl["total"]
        fc = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{T:.3f},asetpts=PTS-STARTPTS,"
              f"afade=t=out:st={T - 0.9:.3f}:d=0.9:curve=qsin,volume=0.8[bg];"
              f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.0[fx];"
              f"[bg][fx]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]")
        return ["-i", mine, "-i", fx], fc, f"weekly music {mine} + sound effects"
    return ["-i", fx], "[1:a]aformat=sample_rates=44100:channel_layouts=stereo[a]", "sound effects only (no assets/weekly.* found)"


def make_weekly_video(out_path, title, subtitle, kicker, ranked):
    tl = timeline(len(ranked))
    data = json.dumps({"title": title, "subtitle": subtitle, "kicker": kicker, "tl": tl,
                       "ranked": [{"name": n, "mins": m} for n, m in ranked]}).replace("</", "<\\/")
    a_args, a_filter, a_desc = audio(os.path.dirname(os.path.abspath(out_path)), tl, len(ranked))
    print("audio:", a_desc)
    return podium.encode(PAGE.replace("__DATA__", data), tl["total"], out_path, a_args, a_filter)
