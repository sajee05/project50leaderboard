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
    return {"total": TOTAL, "p3": 6.9, "p2": 8.0, "p1": 9.75, "confetti": 10.65, "inter": inter,
            "rows": {str(rank): round(start + (n - rank) * inter, 3) for rank in range(4, n + 1)}}


PAGE = r"""<!doctype html><html><head><meta charset='utf-8'><style>
*{box-sizing:border-box;margin:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#1a0b33;color:#fff;
font-family:Inter,-apple-system,'SF Pro Display','Helvetica Neue','Liberation Sans',Arial,sans-serif}
#bg{position:absolute;inset:0;background:
radial-gradient(1100px 800px at 80% 90%,rgba(255,170,70,.55),transparent 65%),
radial-gradient(900px 700px at 10% 10%,rgba(255,70,140,.45),transparent 65%),
linear-gradient(150deg,#1c0b3a 0%,#4a1470 38%,#b3265f 72%,#ff7a45 100%)}
canvas{position:absolute;inset:0}
.abs{position:absolute}
#head{left:0;top:0;transform-origin:0 0;width:900px}
#kick{font-size:24px;letter-spacing:9px;font-weight:800;color:#ffd27a}
#ttl{font-size:104px;font-weight:900;letter-spacing:-3px;line-height:1.05;margin-top:4px}
#sub{display:inline-block;margin-top:10px;font-size:32px;font-weight:700;background:rgba(255,255,255,.16);
border:1px solid rgba(255,255,255,.4);border-radius:14px;padding:8px 24px}
#panel{background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.22);border-radius:36px;padding:24px;
backdrop-filter:blur(10px)}
#grid{display:flex;gap:26px}
.col{flex:1;min-width:0}
.rw{display:flex;align-items:center;gap:12px;padding:0 16px;border-radius:16px;margin-bottom:var(--gap);background:rgba(255,255,255,.10)}
.rw.top{background:linear-gradient(90deg,rgba(255,210,122,.38),rgba(255,255,255,.12))}
.rk{width:2.2em;font-weight:900;color:#ffd27a;font-variant-numeric:tabular-nums}
.rn{width:30%;min-width:0;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar{flex:1;height:.42em;border-radius:99px;background:rgba(255,255,255,.14);overflow:hidden}
.bar i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#ffd27a,#ff7a45)}
.rv{font-weight:900;font-variant-numeric:tabular-nums;min-width:3.3em;text-align:right}
.pil{border-radius:26px 26px 0 0;overflow:hidden;display:flex;justify-content:center;box-shadow:inset 0 0 0 2px rgba(255,255,255,.35)}
.pil b{font-size:130px;font-weight:900;margin-top:10px;color:rgba(40,10,50,.7)}
.g1{background:linear-gradient(160deg,#fff3b0,#ffc83d 45%,#d98a00)}
.g2{background:linear-gradient(160deg,#ffffff,#d6dbe6 45%,#8b95a8)}
.g3{background:linear-gradient(160deg,#ffd9b0,#e89a5a 45%,#a8581f)}
.card{text-align:center}
.av{border-radius:50%;margin:0 auto 10px;display:flex;align-items:center;justify-content:center;font-weight:900;color:#2a0b33;
border:4px solid rgba(255,255,255,.85)}
.nm{font-weight:900;letter-spacing:-.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vl{font-weight:900;font-variant-numeric:tabular-nums;letter-spacing:-1px}
.hl{font-size:18px;letter-spacing:4px;color:rgba(255,255,255,.75);margin-top:2px}
#flash{background:#fff;opacity:0;inset:0}
#fade{background:#12061f;opacity:0;inset:0}
</style></head><body>
<div id='bg'></div><canvas id='cv' width='1920' height='1080'></canvas>
<div id='head' class='abs'><div id='kick'></div><div id='ttl'></div><div id='sub'></div></div>
<div id='panel' class='abs'></div><div id='stage'></div>
<div id='flash' class='abs'></div><div id='fade' class='abs'></div>
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
const inner=PH-48, gap=cols==2?6:8, rh=Math.min(70,Math.floor(inner/per)-gap), fs=Math.max(15,Math.min(30,Math.round(rh*.46)));
const panel=$('panel'); panel.style.cssText+=`left:${PX}px;top:${PY}px;width:${PW}px;height:${PH}px;--gap:${gap}px`;
let h='<div id="grid">';
for(let c=0;c<cols;c++){h+='<div class="col">';
  for(let i=c*per;i<Math.min(n,(c+1)*per);i++){const rank=i+1;
    h+=`<div class="rw ${rank<=3?'top':''}" id="r${rank}" style="height:${rh}px;font-size:${fs}px;opacity:0"><span class="rk">${rank}</span><span class="rn"></span><span class="bar"><i style="width:0%"></i></span><span class="rv"></span></div>`}
  h+='</div>'}
panel.innerHTML=h+'</div>';
R.forEach((p,i)=>{const e=$('r'+(i+1)); e.querySelector('.rn').textContent=p.name; e.dataset.v=p.mins});
const rowT=rank=>rank>3?TL.rows[String(rank)]:(rank==3?TL.p3:rank==2?TL.p2:TL.p1)+0.35;

// ---- podium (right) ----
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
  // sweeping spotlight beams
  ctx.globalCompositeOperation='lighter';
  for(let i=0;i<5;i++){const a=Math.PI/2+Math.sin(t*.7+i*1.9)*.55+(i-2)*.28, len=1500, w=130+40*Math.sin(t+i);
    const ox=1480+(i-2)*60, g=ctx.createLinearGradient(ox,-40,ox+Math.cos(a)*len,-40+Math.sin(a)*len);
    g.addColorStop(0,'rgba(255,230,180,.20)'); g.addColorStop(1,'rgba(255,230,180,0)');
    ctx.fillStyle=g; ctx.beginPath(); ctx.moveTo(ox-14,-40); ctx.lineTo(ox+14,-40);
    ctx.lineTo(ox+Math.cos(a)*len+Math.cos(a+1.57)*w,-40+Math.sin(a)*len+Math.sin(a+1.57)*w);
    ctx.lineTo(ox+Math.cos(a)*len-Math.cos(a+1.57)*w,-40+Math.sin(a)*len-Math.sin(a+1.57)*w); ctx.fill()}
  // bokeh
  for(let i=0;i<26;i++){const x=(rnd(i)*2100+t*(14+rnd(i+4)*22))%2100-90, y=(rnd(i+2)*1200-t*(10+rnd(i+6)*18)+3600)%1200-60, r=10+rnd(i+8)*36;
    ctx.globalAlpha=.07+.12*rnd(i+3); ctx.fillStyle=['#ffd27a','#ff8fb3','#ffffff','#b79bff'][i%4]; ctx.beginPath(); ctx.arc(x,y,r,0,7); ctx.fill()}
  ctx.globalAlpha=1; ctx.globalCompositeOperation='source-over';

  // title: opens big in the centre, glides to the corner on the drop
  const k=eo((t-1.6)/.9), s=1.55-.55*k, px=420*(1-k)+80*k, py=330*(1-k)+46*k, op=eo(t/.7);
  const hd=$('head'); hd.style.opacity=op; hd.style.transform=`translate(${px}px,${py+(1-op)*30}px) scale(${s})`;
  // list panel
  const pa=eo((t-2.3)/.6); panel.style.opacity=pa; panel.style.transform=`translateY(${(1-pa)*40}px)`;

  // rows
  for(let rank=n;rank>=1;rank--){const e=$('r'+rank), rt=rowT(rank), q=eo((t-rt)/.45);
    e.style.opacity=q; e.style.transform=`translateX(${(1-q)*-70}px) scale(${rank<=3?1+.05*Math.sin(clamp((t-rt)/.5)*3.14):1})`;
    e.querySelector('.bar i').style.width=(q*(+e.dataset.v/maxv)*100)+'%';
    e.querySelector('.rv').textContent=q>0?fmt(+e.dataset.v*eo((t-rt)/.7)):''}

  // podium
  for(const rank of [1,2,3]){const e=els[rank]; if(!e) continue; const s0=tm[rank], p=clamp((t-s0)/.9), hh=hts[rank]*eo(p);
    e.pil.style.height=hh+'px'; e.pil.style.top=(base-hh)+'px'; e.pil.style.opacity=p>0?1:0;
    const cp=eb((t-s0-.45)/.6), cardH=rank==1?262:232;
    e.card.style.opacity=clamp((t-s0-.4)/.3); e.card.style.top=(base-hh-cardH-(1-clamp(cp))*36)+'px';
    e.vl.textContent=fmt(e.v*eo((t-s0-.5)/1.1))}
  // winner flash + confetti
  $('flash').style.opacity=clamp(1-(t-TL.p1-.75)/.3)*(t>TL.p1+.75?.5:0);
  const ct=t-TL.confetti;
  if(ct>0&&ct<2.6){for(let i=0;i<190;i++){const side=i%2?1:-1, a=(-90+side*(18+rnd(i)*40))*Math.PI/180, sp=600+rnd(i+1)*900, dl=rnd(i+2)*.2, tt=ct-dl; if(tt<0) continue;
      const kk=Math.exp(-tt*1.15), x=cx+side*130+Math.cos(a)*sp*(1-kk)/1.15+Math.sin(tt*4+i)*12, y=base-hts[1]+Math.sin(a)*sp*(1-kk)/1.15+650*tt*tt;
      ctx.save(); ctx.translate(x,y); ctx.rotate(tt*(3+rnd(i+4)*7)+i); ctx.globalAlpha=clamp(1-(ct-1.7)/.9);
      ctx.fillStyle=['#ffd27a','#ffffff','#ff5e8a','#7ef0c8','#9bb3ff'][i%5]; if(i%3==0){ctx.beginPath();ctx.arc(0,0,5,0,7);ctx.fill()} else ctx.fillRect(-6,-3,12,6); ctx.restore()}ctx.globalAlpha=1}
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
    add(tl["p1"] - 0.6, 0.6, swell(0.6), 0.24)          # winner build-up
    add(tl["p1"], 1.4, boom, 0.95)
    for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        add(tl["p1"] + 0.05 + k * 0.09, 1.6, ding(f), 0.26)
    add(tl["confetti"], 0.35, pop, 0.45)                # confetti pop + sparkle
    for k in range(16):
        add(tl["confetti"] + 0.05 + k * 0.08, 0.5, star(1500 + 110 * (k % 6)), 0.07)
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
