"""Animated leaderboard video: podium reveal for the top 3, then every other member rolls in.
Deterministic: an HTML page exposes render(t); we step t frame by frame, screenshot with
Playwright and pipe the JPEGs into ffmpeg (free: runs on the standard GitHub Actions runner)."""
import html, json, os, subprocess

FPS = 30
W, H = 1920, 1080

PAGE = r"""<!doctype html><html><head><meta charset='utf-8'><style>
*{box-sizing:border-box;margin:0}
html,body{width:1920px;height:1080px;overflow:hidden;background:#07080d;color:#f5f5f7;
font-family:Inter,-apple-system,'SF Pro Display','Helvetica Neue','Liberation Sans',Arial,sans-serif}
#bg{position:absolute;inset:0;background:
radial-gradient(900px 700px at 28% 70%,rgba(70,90,255,.22),transparent 70%),
radial-gradient(800px 600px at 85% 15%,rgba(255,170,60,.13),transparent 70%),
linear-gradient(160deg,#0b0d18,#06070b)}
canvas{position:absolute;inset:0}
.abs{position:absolute}
#kick{left:96px;top:70px;font-size:22px;letter-spacing:7px;font-weight:700;color:#8b93ff}
#ttl{left:92px;top:104px;font-size:84px;font-weight:800;letter-spacing:-2.5px}
#sub{left:96px;top:208px;font-size:32px;font-weight:700;color:#fff;background:rgba(139,147,255,.18);border:1px solid rgba(139,147,255,.35);border-radius:999px;padding:8px 26px}
.pil{border-radius:30px 30px 0 0;overflow:hidden;display:flex;justify-content:center;
box-shadow:0 0 60px rgba(0,0,0,.4) inset}
.pil b{font-size:150px;font-weight:800;margin-top:14px;opacity:.9;color:rgba(10,10,20,.78)}
.g1{background:linear-gradient(180deg,#ffd45e,#c98a10)}
.g2{background:linear-gradient(180deg,#e9edf3,#8e97a6)}
.g3{background:linear-gradient(180deg,#f0b27a,#a8642d)}
.card{text-align:center}
.av{border-radius:50%;margin:0 auto 12px;display:flex;align-items:center;justify-content:center;
font-weight:800;color:#0b0c14}
.nm{font-weight:800;letter-spacing:-.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vl{font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-1px}
.hl{font-size:20px;color:#9a9aa8;letter-spacing:3px;margin-top:2px}
#panel{background:rgba(255,255,255,.055);border:1px solid rgba(255,255,255,.09);border-radius:34px;
padding:28px 30px;backdrop-filter:blur(8px)}
#ph{font-size:20px;letter-spacing:5px;font-weight:700;color:#9a9aa8;margin-bottom:12px}
#grid{display:flex;gap:30px}
.col{flex:1;min-width:0}
.rw{display:flex;align-items:center;border-bottom:1px solid rgba(255,255,255,.07)}
.rk{width:46px;font-weight:800;color:#8b93ff;font-variant-numeric:tabular-nums}
.rn{flex:1;min-width:0;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rv{font-weight:800;font-variant-numeric:tabular-nums;margin-left:12px}
.rb{height:6px;border-radius:3px;background:rgba(255,255,255,.1);margin-left:14px;overflow:hidden;flex:none}
.rb i{display:block;height:100%;border-radius:3px;background:linear-gradient(90deg,#6b78ff,#9be7ff)}
</style></head><body>
<div id='bg'></div><canvas id='cv' width='1920' height='1080'></canvas>
<div id='kick' class='abs'></div><div id='ttl' class='abs'></div><div id='sub' class='abs'></div>
<div id='stage'></div><div id='panel' class='abs'></div>
<script>
const D=__DATA__;
const TOTAL=D.total, ctx=document.getElementById('cv').getContext('2d');
const $=id=>document.getElementById(id), clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const eo=x=>1-Math.pow(1-clamp(x),3), eb=x=>{x=clamp(x);const c=1.5;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2)};
const fmt=m=>{m=Math.round(m);return Math.floor(m/60)+':'+String(m%60).padStart(2,'0')};
function rnd(i){const x=Math.sin(i*127.1+311.7)*43758.5453;return x-Math.floor(x)}
$('kick').textContent=D.kicker; $('ttl').textContent=D.title; $('sub').textContent=D.subtitle;

const rest=D.rest, n=rest.length, cols=n>12?2:1;
const panelW=cols==2?920:600, panelX=1920-80-panelW;
const pw=cols==2?236:290, gap=cols==2?14:22, cx=n? (80+(panelX-40-80)/2) : 960;
const base=985, hts=[440,330,240];            // 1st, 2nd, 3rd pillar heights
const order=[[1,1],[0,0],[2,2]];             // [slot position index, podium index]
const slotX=[cx-(pw+gap), cx, cx+(pw+gap)];  // 2nd, 1st, 3rd
const T={3:[1.2,1.0],2:[3.0,1.0],1:[5.0,1.1]}; // rank -> [start, rise]
const stage=$('stage'); const els={};
D.top.forEach((p,i)=>{                       // i = 0,1,2 -> rank 1,2,3
  const rank=i+1, x=rank==1?slotX[1]:rank==2?slotX[0]:slotX[2], h=hts[i];
  const pil=document.createElement('div'); pil.className='abs pil g'+rank;
  pil.style.cssText+=`left:${x-pw/2}px;width:${pw}px;`; pil.innerHTML='<b>'+rank+'</b>'; stage.appendChild(pil);
  const card=document.createElement('div'); card.className='abs card'; card.style.cssText+=`left:${x-pw/2-20}px;width:${pw+40}px`;
  const av=rank==1?120:100, init=(p.name.trim()[0]||'?').toUpperCase();
  card.innerHTML=`<div class='av g${rank}' style='width:${av}px;height:${av}px;font-size:${av*.45}px'>${init}</div>
  <div class='nm' style='font-size:${rank==1?48:40}px'></div><div class='vl' style='font-size:${rank==1?64:54}px'></div><div class='hl'>HOURS</div>`;
  card.querySelector('.nm').textContent=p.name; stage.appendChild(card);
  els[rank]={pil,card,h,v:p.mins,vl:card.querySelector('.vl')};
});
// rest panel
const panel=$('panel'); panel.style.cssText+=`left:${panelX}px;top:${n?190:2000}px;width:${panelW}px`;
const perCol=Math.ceil(n/cols), avail=760-(cols==2?0:0), rh=Math.min(84,Math.floor(avail/Math.max(perCol,1)));
const fs=Math.max(17,Math.min(30,Math.round(rh*.42)));
const maxv=Math.max(1,...D.top.map(p=>p.mins),...rest.map(p=>p.mins));
let html='<div id="ph">'+D.listLabel+'</div><div id="grid">';
for(let c=0;c<cols;c++){html+='<div class="col">';
  for(let i=c*perCol;i<Math.min(n,(c+1)*perCol);i++){const p=rest[i];
    html+=`<div class="rw" id="r${i}" style="height:${rh}px;font-size:${fs}px"><span class="rk">${i+4}</span><span class="rn"></span>
    <span class="rb" style="width:${cols==2?70:120}px"><i style="width:${Math.max(2,p.mins/maxv*100)}%"></i></span><span class="rv">${fmt(p.mins)}</span></div>`}
  html+='</div>'}
panel.innerHTML=html+'</div>';
rest.forEach((p,i)=>{const r=$('r'+i); if(r) r.querySelector('.rn').textContent=p.name});
const listStart=8.2, perRow=Math.min(.12,3.4/Math.max(n,1));

function render(t){
  ctx.clearRect(0,0,1920,1080);
  // drifting dust
  for(let i=0;i<70;i++){const x=(rnd(i)*1920+t*(8+rnd(i+9)*14))%1920,y=(rnd(i+3)*1080-t*(6+rnd(i+5)*10)+3240)%1080;
    ctx.globalAlpha=.10+.25*rnd(i+7);ctx.fillStyle='#cfd6ff';ctx.beginPath();ctx.arc(x,y,1+rnd(i+11)*2.2,0,7);ctx.fill()}
  ctx.globalAlpha=1;
  const hdr=eo(t/.9);
  for(const id of ['kick','ttl','sub']){const e=$(id);e.style.opacity=hdr;e.style.transform=`translateY(${(1-hdr)*24}px)`}
  // glow behind 1st
  const g1=clamp((t-T[1][0])/1.2);
  if(g1>0){const gr=ctx.createRadialGradient(slotX[1],520,10,slotX[1],520,520);
    gr.addColorStop(0,`rgba(255,200,80,${.35*g1})`);gr.addColorStop(1,'rgba(255,200,80,0)');ctx.fillStyle=gr;ctx.fillRect(0,0,1920,1080)}
  for(const rank of [1,2,3]){const e=els[rank]; if(!e) continue;
    const [s,d]=T[rank], p=clamp((t-s)/d), hh=e.h*eo(p);
    e.pil.style.height=hh+'px'; e.pil.style.top=(base-hh)+'px'; e.pil.style.opacity=p>0?1:0;
    const cp=eb((t-s-d*.55)/.7);
    e.card.style.opacity=clamp((t-s-d*.5)/.4);
    const cardH=rank==1?285:255; e.card.style.top=(base-hh-cardH-(1-clamp(cp))*30)+'px';
    e.vl.textContent=fmt(e.v*eo((t-s-d*.6)/1.4));
  }
  // confetti from the winner's pillar
  const ct=t-(T[1][0]+T[1][1]-.1);
  if(ct>0&&ct<3.6){for(let i=0;i<170;i++){const a=(-90+(rnd(i)-.5)*110)*Math.PI/180,sp=500+rnd(i+1)*900,dl=rnd(i+2)*.25;
      const tt=ct-dl; if(tt<0) continue; const k=Math.exp(-tt*1.1);
      const x=slotX[1]+Math.cos(a)*sp*(1-k)/1.1+Math.sin(tt*3+i)*14,y=base-hts[0]+Math.sin(a)*sp*(1-k)/1.1+700*tt*tt;
      ctx.save();ctx.translate(x,y);ctx.rotate(tt*(3+rnd(i+4)*6)+i);ctx.globalAlpha=clamp(1-(ct-2.4)/1.2);
      ctx.fillStyle=['#ffd45e','#ffffff','#7c8bff','#ff7ab6','#7ef0c8'][i%5];ctx.fillRect(-6,-3,12,6);ctx.restore()}ctx.globalAlpha=1}
  // list
  const pa=eo((t-listStart+.3)/.8); panel.style.opacity=n?pa:0; panel.style.transform=`translateX(${(1-pa)*80}px)`;
  for(let i=0;i<n;i++){const r=$('r'+i),q=eo((t-listStart-i*perRow)/.5);
    r.style.opacity=q;r.style.transform=`translateX(${(1-q)*60}px)`}
}
window.render=render; window.TOTAL=TOTAL;
</script></body></html>"""


# ---------- original soundtrack (synthesised here, so no licensing issues) ----------
def make_music(total, path, rate=44100, sfx_only=False):
    """Upbeat 120 bpm loop (I-V-vi-IV) with a hit on each podium rise and a fanfare on the winner's reveal.
    sfx_only=True keeps just the hits / whoosh / fanfare / sparkle, to layer over a track you supply."""
    import array, math, random, wave
    n = int(total * rate)
    L = [0.0] * n
    rnd = random.Random(5)

    def add(t0, dur, fn, gain):
        i0, cnt = int(t0 * rate), int(dur * rate)
        for k in range(cnt):
            i = i0 + k
            if i >= n:
                break
            L[i] += fn(k / rate) * gain

    def pluck(freq, dur=0.32):
        return lambda t: (math.sin(6.283 * freq * t) + .35 * math.sin(12.566 * freq * t) + .15 * math.sin(18.85 * freq * t)) \
            * math.exp(-t * 9) * min(1, t * 400)

    def bass(freq):
        return lambda t: math.sin(6.283 * freq * t) * math.exp(-t * 4) * min(1, t * 300)

    def kick(t):
        return math.sin(6.283 * (45 * t + 70 * (1 - math.exp(-t * 28)) / 28 * 28 / 28 * 0.0 + 75 * (1 - math.exp(-t * 30)) / 30)) * math.exp(-t * 11)

    def hat(t):
        return (rnd.random() * 2 - 1) * math.exp(-t * 55)

    def thump(t):  # impact for a podium rise
        return math.sin(6.283 * (38 + 60 * math.exp(-t * 9)) * t) * math.exp(-t * 3.2)

    def whoosh(t):  # rising noise before the hit
        return (rnd.random() * 2 - 1) * (t / 0.5) ** 2 * (1 if t < 0.5 else 0)

    chords = [(261.63, [261.63, 329.63, 392.0]), (196.0, [196.0, 246.94, 293.66]),
              (220.0, [220.0, 261.63, 329.63]), (174.61, [174.61, 220.0, 261.63])]
    beat = 0.5
    t, step = 0.0, 0
    while t < total and not sfx_only:
        bar = int(t / (4 * beat)) % 4
        root, tones = chords[bar]
        b = int(round(t / beat))
        if t >= 0.5:
            if step % 2 == 0:
                add(t, 0.5, bass(root / 2 if root > 200 else root), 0.34)
            add(t, 0.3, pluck(tones[step % 3] * 2), 0.16)              # 8th-note arpeggio on every step
            if t >= 1.0 and step % 2 == 0:
                add(t, 0.35, kick, 0.5)
            if step % 2 == 1:
                add(t, 0.12, hat, 0.09)
        step += 1
        t += beat / 2
    # podium hits (match the video: 3rd at 1.2s, 2nd at 3.0s, 1st at 5.0s)
    for ht, g in ((1.2, .55), (3.0, .62), (5.0, .8)):
        add(ht - 0.5, 0.5, whoosh, 0.22)
        add(ht, 1.2, thump, g)
    # winner fanfare + confetti sparkle
    for k, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
        add(5.75 + k * 0.1, 1.2, pluck(f), 0.3)
    for k in range(14):
        add(6.0 + k * 0.09, 0.4, pluck(1568 + 90 * (k % 5)), 0.07)
    peak = max(abs(x) for x in L) or 1
    fade = int(1.6 * rate)
    out = array.array("h")
    for i, x in enumerate(L):
        g = 0.85 / peak * min(1, (n - i) / fade) * min(1, i / (0.05 * rate))
        out.append(int(max(-1, min(1, x * g)) * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    return path


def audio_input(total, workdir):
    """Returns (ffmpeg input args, filter_complex, description) for the audio.
    MUSIC_FILE or assets/music.* is used as background music: trimmed from its start to the video length
    (looped if shorter), with a smooth 1.5 s fade-out, and the sound effects are layered on top.
    With no file, the built-in original score is used."""
    import glob
    mine = os.environ.get("MUSIC_FILE") or next(iter(sorted(glob.glob("assets/music.*"))), "")
    if mine and os.path.exists(mine):
        fx = os.path.join(workdir, "podium_sfx.wav")
        make_music(total, fx, sfx_only=True)
        st = max(0.0, total - 1.5)
        fc = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
              f"afade=t=in:st=0:d=0.4,afade=t=out:st={st:.3f}:d=1.5:curve=qsin,volume=0.75[bg];"
              f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.9[fx];"
              f"[bg][fx]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]")
        return ["-stream_loop", "-1", "-i", mine, "-i", fx], fc, f"your music {mine} + sound effects"
    wav = os.path.join(workdir, "podium_music.wav")
    make_music(total, wav)
    return ["-i", wav], "[1:a]anull[a]", "built-in score"

def build_page(title, subtitle, kicker, ranked, list_label="THE REST OF THE BOARD", hold=3.0):
    """ranked: [(name, minutes), ...] already sorted best-first (any length, up to ~30)."""
    top = [{"name": n, "mins": m} for n, m in ranked[:3]]
    rest = [{"name": n, "mins": m} for n, m in ranked[3:]]
    list_start = 8.2 if rest else 7.5
    total = (list_start + 0.6 + min(.12 * len(rest), 3.4) + hold) if rest else (7.5 + hold)
    data = json.dumps({"title": title, "subtitle": subtitle, "kicker": kicker, "top": top, "rest": rest,
                       "listLabel": list_label, "total": total}).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data), total


def make_video(out_path, title, subtitle, kicker, ranked, list_label="THE REST OF THE BOARD", fps=FPS):
    from playwright.sync_api import sync_playwright
    page_html, total = build_page(title, subtitle, kicker, ranked, list_label)
    a_args, a_filter, a_desc = audio_input(total, os.path.dirname(os.path.abspath(out_path)))
    print("audio:", a_desc)
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-", *a_args,
         "-filter_complex", a_filter, "-map", "0:v", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)
    frames = int(total * fps)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(page_html)
        for i in range(frames):
            pg.evaluate("t=>render(t)", i / fps)
            ff.stdin.write(pg.screenshot(type="jpeg", quality=88))
        b.close()
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    return total
