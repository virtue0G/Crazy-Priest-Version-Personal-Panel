"""把知识库渲染成星图。

读 kb/*.md，抽出条目与 [[链接]]，生成一张自包含的 星图.html。

为什么是"星图"而不是普通关系图：
  · 知识库的**形状就是它的链接**——文本看不见，星图看得见
  · 领域靠**位置**分辨（像星座），不靠颜色
  · 颜色只编码一个量：**被多少条链接指向**（枢纽概念更亮）

配色经 dataviz 验证器校验：
  node ramp  #26573f → #3d9b78 → #58c9a3 → #9df0cf  (ordinal, dark, 全项 PASS)
  星图里任意两颗星都可能相邻，属"全配对"场景，全配对下分类色最多 3 个，
  所以领域**不能用颜色区分**——改用位置聚类 + 区域标签。
"""
import json
import re
from pathlib import Path

KB = Path(__file__).parent
OUT = KB / "星图.html"

# 领域（按文件名），锚点角度在渲染时按节点数分配
DOMAINS = [
    ("01", "MMM 建模"), ("02", "零售渠道"), ("03", "品牌资产"),
    ("04", "数据工程"), ("05", "AI 与提示词"), ("06", "沟通与工作"),
    ("07", "思维方法"),
]

# 顺序色阶（已通过 --ordinal 校验），按"被链接次数"分 4 档
RAMP = ["#337054", "#4ab389", "#6bdbb2", "#b0f8dd"]
BINS = [2, 5, 9]          # 1-2 / 3-5 / 6-9 / 10+


def norm(s: str) -> str:
    return re.sub(r"[\s·、/（）()：:？?，,。．\._\-—]", "", s).lower()


# ── 条目正文转 HTML（在构建期做，浏览器端只负责显示）──────────────
def _inline(t: str) -> str:
    t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    # [[链接]] → 可点击，点了跳去那条
    t = re.sub(r"\[\[([^\]]+)\]\]",
               lambda m: '<a class="wl" data-t="%s">%s</a>'
                         % (m.group(1).replace('"', "&quot;"), m.group(1)), t)
    return t


def _table(rows):
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]
    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    h = "".join(f"<th>{_inline(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def _list(items):
    # items: [(层级, html)]
    out, stack = [], 0
    for lvl, txt in items:
        if lvl > stack:
            out.append("<ul>" * (lvl - stack)); stack = lvl
        elif lvl < stack:
            out.append("</ul>" * (stack - lvl)); stack = lvl
        out.append(f"<li>{txt}</li>")
    out.append("</ul>" * stack)
    return "".join(out)


def md_to_html(md: str) -> str:
    lines, out, i = md.split(chr(10)), [], 0
    while i < len(lines):
        st = lines[i].strip()
        if not st:
            i += 1
            continue
        if st.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i]); i += 1
            out.append(_table(rows) if len(rows) >= 2 else "")
            continue
        if st.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip()); i += 1
            out.append("<blockquote>" + _inline(" ".join(buf)) + "</blockquote>")
            continue
        if st in ("---", "***", "___"):
            out.append("<hr>"); i += 1; continue
        m = re.match(r"^#{3,6}\s+(.*)$", st)
        if m:
            out.append(f"<h5>{_inline(m.group(1))}</h5>"); i += 1; continue
        if re.match(r"^([-*]|\d+[.、)])\s+", st):
            items, base = [], None
            while i < len(lines):
                m2 = re.match(r"^(\s*)([-*]|\d+[.、)])\s+(.*)$", lines[i])
                if not m2:
                    break
                ind = len(m2.group(1))
                if base is None:
                    base = ind
                items.append((1 if ind <= base else 2, _inline(m2.group(3).strip())))
                i += 1
            out.append(_list(items))
            continue
        out.append(f"<p>{_inline(st)}</p>")
        i += 1
    return "".join(out)


def parse():
    entries, links = [], []
    for pre, name in DOMAINS:
        f = next(KB.glob(f"{pre}-*.md"), None)
        if not f:
            continue
        src = f.read_text(encoding="utf-8")
        # 只取正文条目，另见指针不建节点（它是重定向）
        for m in re.finditer(r"^### (?!另见)(\S+?)｜(.+)$", src, re.M):
            kind, title = m.group(1), m.group(2).strip()
            # 该条目到下一个 ### 之间的正文里的链接
            rest = src[m.end():]
            nxt = re.search(r"^### ", rest, re.M)
            body = rest[: nxt.start()] if nxt else rest
            outs = [t.strip() for t in re.findall(r"\[\[([^\]]+)\]\]", body)]
            entries.append({"t": title, "k": kind, "d": pre, "o": outs,
                            "h": md_to_html(body)})

    idx = {norm(e["t"]): i for i, e in enumerate(entries)}
    matched, gaps = set(), {}
    for i, e in enumerate(entries):
        for raw in e["o"]:
            n = norm(raw)
            j = idx.get(n)
            if j is None:                       # 模糊匹配
                for k, v in idx.items():
                    if n and (n in k or k in n):
                        j = v
                        break
            if j is not None and j != i:
                links.append((i, j))
                matched.add(raw)
            elif j is None:
                gaps.setdefault(raw, 0)
                gaps[raw] += 1

    # 去重边
    links = sorted(set(links))
    indeg = [0] * len(entries)
    for _, j in links:
        indeg[j] += 1

    # 悬空链接：被指向却没有条目的概念——网络的边界
    gap_nodes = [{"t": t, "n": c} for t, c in
                 sorted(gaps.items(), key=lambda x: -x[1]) if c >= 1 and t not in matched]

    for i, e in enumerate(entries):
        e["deg"] = indeg[i]      # 被引次数。别叫 i —— JS 的 .map((n,i)) 会把 i 覆盖成下标
        e.pop("o")
    return entries, links, gap_nodes


def main():
    entries, links, gaps = parse()
    # 每条跨领域边的领域对，用于统计
    cross = sum(1 for a, b in links if entries[a]["d"] != entries[b]["d"])
    data = {
        "nodes": entries,
        "links": links,
        "gaps": gaps,
        "domains": [{"id": p, "name": n} for p, n in DOMAINS],
        "ramp": RAMP,
        "bins": BINS,
        "stats": {
            "nodes": len(entries), "links": len(links),
            "cross": cross, "gaps": len(gaps),
        },
    }
    html = TEMPLATE.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    s = data["stats"]
    print(f"✓ 星图已生成 {OUT}")
    print(f"  {s['nodes']} 颗星 · {s['links']} 条连线（其中跨领域 {s['cross']} 条）· {s['gaps']} 个悬空概念")
    return OUT


TEMPLATE = r"""<title>知识星图</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@300;400;500&family=Rajdhani:wght@500;700&display=swap">
<style>
  :root{
    color-scheme: dark;
    --bg:#0a0d0f; --panel:#0e1315; --line:#1d2729;
    --ink:#eef4f1; --mut:#9daba6; --dim:#71817c;
    --n1:#337054; --n2:#4ab389; --n3:#6bdbb2; --n4:#b0f8dd;
    --cross:#c9a44c; --gap:#3a4a4d; --sel:#9df0cf;
    --sans:"Noto Sans SC","PingFang SC",sans-serif; --num:"Rajdhani",sans-serif;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-weight:300;
    font-size:13px;overflow:hidden}
  #cv{display:block;width:100%;height:100%;cursor:grab}
  #cv.drag{cursor:grabbing}

  /* 顶栏 */
  header{position:fixed;top:0;left:0;right:0;z-index:10;padding:14px 18px;
    display:flex;gap:18px;align-items:baseline;flex-wrap:wrap;
    background:linear-gradient(180deg,rgba(10,13,15,.94),rgba(10,13,15,0));
    padding-top:calc(14px + env(safe-area-inset-top,0px))}
  h1{font-size:14px;font-weight:500;letter-spacing:.24em;color:var(--ink)}
  .st{font-family:var(--num);font-size:12px;color:var(--mut);font-variant-numeric:tabular-nums}
  .st b{color:var(--n3);font-weight:700}
  .st i{font-style:normal;color:var(--dim);margin:0 5px}

  /* 图例 + 筛选 */
  aside{position:fixed;z-index:10;left:18px;bottom:calc(18px + env(safe-area-inset-bottom,0px));
    display:flex;flex-direction:column;gap:14px;max-width:min(310px,calc(100vw - 36px))}
  .box{background:rgba(14,19,21,.9);border:1px solid var(--line);border-radius:11px;padding:13px 15px}
  .bt{font-size:10px;letter-spacing:.22em;color:var(--dim);margin-bottom:9px}
  .ramp{display:flex;flex-direction:column;gap:6px}
  .ramp div{display:flex;align-items:center;gap:9px;font-size:11.5px;color:var(--mut)}
  .dot{border-radius:50%;flex:none}
  .lg{display:flex;flex-wrap:wrap;gap:6px}
  .chip{font-size:11.5px;padding:4px 11px;border:1px solid var(--line);border-radius:20px;
    color:var(--mut);cursor:pointer;user-select:none;background:transparent;font-family:inherit;
    transition:border-color .12s,color .12s}
  .chip:hover{border-color:var(--n3);color:var(--ink)}
  .chip[aria-pressed="true"]{border-color:var(--n3);color:var(--bg);background:var(--n3);font-weight:400}
  .hint{font-size:11px;color:var(--dim);line-height:1.75}

  /* 详情卡 */
  #det{position:fixed;z-index:12;right:18px;top:64px;width:min(520px,calc(100vw - 36px));
    max-height:calc(100vh - 110px);overflow-y:auto;
    background:var(--panel);border:1px solid #2c4a3f;border-radius:13px;padding:17px 19px;
    display:none}
  #det.on{display:block}
  #det .t{font-size:16px;font-weight:500;line-height:1.5;padding-right:24px}
  #det .m{font-size:11px;color:var(--dim);margin-top:6px;display:flex;gap:9px;flex-wrap:wrap}
  #det .m em{font-style:normal;color:var(--n3)}
  #det .x{position:absolute;top:12px;right:14px;cursor:pointer;color:var(--dim);font-size:17px;
    line-height:1;background:none;border:none;padding:4px}
  #det .x:hover{color:var(--ink)}
  #det .lb{font-size:10px;letter-spacing:.2em;color:var(--dim);margin:16px 0 7px}
  /* 正文：这是面板的主角，行距放宽、层级拉开 */
  #det .body{font-size:13.5px;color:#ccd8d3;line-height:1.9;margin-top:13px}
  #det .body p{margin:0 0 8px}
  #det .body>b:first-child{color:#eef4f1}
  #det .body b{color:#eef4f1;font-weight:500}
  #det .body ul{margin:4px 0 10px;padding:0;list-style:none}
  #det .body>ul>li{position:relative;padding-left:13px;margin:3px 0}
  #det .body>ul>li::before{content:"";position:absolute;left:0;top:10px;width:4px;height:4px;
    border-radius:50%;background:var(--n2)}
  #det .body ul ul{margin:3px 0 3px 8px}
  #det .body ul ul li{position:relative;padding-left:12px;color:#b3c0bb;font-size:13px}
  #det .body ul ul li::before{content:"";position:absolute;left:0;top:9px;width:3px;height:3px;
    border-radius:50%;background:var(--dim)}
  #det .body blockquote{margin:9px 0;padding:9px 13px;border-left:2px solid var(--n2);
    background:rgba(74,179,137,.08);border-radius:0 7px 7px 0;color:#c4d0cb}
  #det .body h5{font-size:11.5px;letter-spacing:.16em;color:var(--n4);margin:14px 0 6px}
  #det .body hr{border:none;border-top:1px dashed var(--line);margin:12px 0}
  #det .body code{font-family:var(--num);background:rgba(255,255,255,.06);
    padding:1px 5px;border-radius:4px;font-size:12.5px;color:#dceee7}
  #det .body .tw{overflow-x:auto;margin:9px 0}
  #det .body table{border-collapse:collapse;font-size:12.5px}
  #det .body th{text-align:left;color:var(--dim);font-weight:500;font-size:10.5px;
    letter-spacing:.1em;padding:0 12px 6px 0;border-bottom:1px solid var(--line2);white-space:nowrap}
  #det .body td{padding:6px 12px 6px 0;border-bottom:1px solid var(--line);
    color:#c4d0cb;vertical-align:top}
  /* 正文里的 [[链接]] 可点，点了跳去那条 */
  #det .body a.wl{color:var(--n4);text-decoration:none;
    border-bottom:1px dotted rgba(176,248,221,.45);cursor:pointer}
  #det .body a.wl:hover{color:#fff;border-bottom-color:#fff}
  #det .none{font-size:12.5px;color:var(--dim)}
  #det ul{list-style:none;display:flex;flex-direction:column;gap:5px}
  #det li{font-size:12px;color:var(--mut);padding-left:11px;position:relative;cursor:pointer}
  #det li::before{content:"";position:absolute;left:0;top:8px;width:4px;height:4px;
    border-radius:50%;background:var(--n2)}
  #det li:hover{color:var(--n4)}
  #det li.gap::before{background:var(--gap)}
  #det .none{font-size:12px;color:var(--dim)}

  /* 搜索 */
  #q{width:100%;background:#070d0f;border:1px solid var(--line);border-radius:8px;
    color:var(--ink);padding:7px 11px;font-family:inherit;font-size:12.5px;font-weight:300}
  #q:focus{outline:none;border-color:var(--n3)}
  #q::placeholder{color:var(--dim)}

  @media (max-width:720px){
    aside{gap:9px}
    .box{padding:10px 12px}
    #det{right:9px;left:9px;width:auto;top:auto;bottom:calc(9px + env(safe-area-inset-bottom,0px));
      max-height:62vh}
    aside{max-width:none;right:9px;left:9px}
    .hint{display:none}
  }
</style>

<canvas id="cv"></canvas>

<header>
  <h1>知识星图</h1>
  <div class="st" id="stat"></div>
</header>

<aside>
  <div class="box">
    <div class="bt">搜 索</div>
    <input id="q" placeholder="输入概念名…" autocomplete="off" spellcheck="false">
  </div>
  <div class="box">
    <div class="bt">领 域</div>
    <div class="lg" id="chips"></div>
    <div class="hint" style="margin-top:11px">领域靠位置分辨，不靠颜色</div>
  </div>
  <div class="box" id="lgbox">
    <div class="bt">亮 度 ＝ 被 引 次 数</div>
    <div class="ramp" id="ramp"></div>
    <div class="hint" style="margin-top:11px">
      <span style="color:var(--cross)">━</span> 跨领域连线
      <span style="color:var(--gap)">○</span> 悬空概念（无条目）
    </div>
  </div>
</aside>

<div id="det">
  <button class="x" id="dx" aria-label="关闭">×</button>
  <div class="t" id="dt"></div>
  <div class="m" id="dm"></div>
  <div class="body" id="db"></div>
  <div class="lb">指 向</div>
  <ul id="dout"></ul>
  <div class="lb">被 指 向</div>
  <ul id="din"></ul>
</div>

<script>
const D = /*__DATA__*/;
const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
let W=0, H=0, DPR=1;

/* ── 建图 ─────────────────────────────────────────── */
const nodes = D.nodes.map((n,idx)=>({...n, idx, x:0, y:0, vx:0, vy:0, r:0}));
const gaps  = D.gaps.map((g,i)=>({t:g.t, n:g.n, gi:i, x:0, y:0, vx:0, vy:0, r:0}));

const idxOf = {}; D.nodes.forEach((n,i)=>idxOf[norm(n.t)]=i);
function norm(s){return (s||'').replace(/[\s·、/（）()：:？?，,。．\._\-—]/g,'').toLowerCase()}

const E = D.links.map(([a,b])=>({a, b, cross: D.nodes[a].d !== D.nodes[b].d}));

/* 领域锚点：按节点数分配角度，让星座大小与内容量相称 */
const domCount = {};
D.nodes.forEach(n=>domCount[n.d]=(domCount[n.d]||0)+1);
const doms = D.domains.filter(d=>domCount[d.id]);
let acc = -Math.PI/2;
const domAnchor = {};
const total = D.nodes.length;
doms.forEach(d=>{
  const share = domCount[d.id]/total, span = share*Math.PI*2;
  const a = acc + span/2; acc += span;
  domAnchor[d.id] = {a, share, n: domCount[d.id]};
});

let filter = null, sel = null, hover = null, query = '';
let raw = null, domRaw = null;   // 原始坐标快照，供 fit() 反复缩放

function layout(){
  // 锚点摆在环上；小领域收在内圈、大领域撑到外圈，让每个星座都有地方展开
  const R = Math.min(W*0.5, H*0.5) * 0.86;
  doms.forEach(d=>{
    const A = domAnchor[d.id];
    const rr = R * (0.58 + 0.42*Math.sqrt(A.share*3.2));
    A.x = W/2 + Math.cos(A.a)*rr;
    A.y = H/2 + Math.sin(A.a)*rr*0.80;
    // 区域半径按节点数给足，节点靠碰撞自然铺开
    A.rad = Math.max(92, Math.sqrt(A.n)*34);
  });
  // 初始化：撒在各锚点周围。每次都重撒——否则 fit() 反复缩放会累积
  nodes.forEach(n=>{
    const A = domAnchor[n.d] || {x:W/2,y:H/2,rad:80};
    n.x = A.x + (Math.random()-.5)*A.rad*1.6;
    n.y = A.y + (Math.random()-.5)*A.rad*1.6;
    n.vx = n.vy = 0;
  });
  gaps.forEach((g,i)=>{
    const a = (i/gaps.length)*Math.PI*2;
    g.x = W/2 + Math.cos(a)*R*1.32;
    g.y = H/2 + Math.sin(a)*R*1.32*0.82;
    g.vx = g.vy = 0;
  });
}

/* 半径与亮度分档 */
function tally(v){ const b=D.bins; return v<=b[0]?0 : v<=b[1]?1 : v<=b[2]?2 : 3; }
// 星点要小——它是"星"，不是"球"。信息量交给亮度与标签，不交给面积。
nodes.forEach(n=>{ n.bin = tally(n.deg); n.r = 1.8 + Math.sqrt(n.deg)*1.25; });

/* ── 力导 ─────────────────────────────────────────── */
function step(alpha){
  const k = alpha, N = nodes.length;

  // ① 斥力：范围放宽到 ~420px，否则远节点吸不到位
  for(let i=0;i<N;i++){
    const a=nodes[i];
    for(let j=i+1;j<N;j++){
      const b=nodes[j];
      let dx=b.x-a.x, dy=b.y-a.y, d2=dx*dx+dy*dy;
      if(d2<1){ dx=(Math.random()-.5); dy=(Math.random()-.5); d2=1; }
      if(d2>176400) continue;
      const d=Math.sqrt(d2);
      const f = 3400*k/d2;
      const ux=dx/d, uy=dy/d;
      a.vx-=ux*f; a.vy-=uy*f; b.vx+=ux*f; b.vy+=uy*f;
    }
  }

  // ② 弹力：跨领域的长、同领域的短，让星座内部紧、星座之间松
  E.forEach(e=>{
    const a=nodes[e.a], b=nodes[e.b];
    const dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy)||1;
    const L = e.cross ? 230 : 74;
    const f = (d-L)/d * (e.cross?0.012:0.05) * k;
    a.vx+=dx*f; a.vy+=dy*f; b.vx-=dx*f; b.vy-=dy*f;
  });

  // ③ 领域聚拢：只在飘出本领域范围时才拉回——不是往一个点上吸
  nodes.forEach(n=>{
    const A = domAnchor[n.d]; if(!A) return;
    const dx=A.x-n.x, dy=A.y-n.y, d=Math.hypot(dx,dy)||1;
    if(d > A.rad){
      const pull = (d-A.rad)*0.060*k/d;
      n.vx += dx*pull; n.vy += dy*pull;
    }
  });

  // ④ 碰撞：硬性最小间距。缺了这步，节点会无限重叠成一坨——
  //    这就是第一版六个"毛球"的成因。
  for(let i=0;i<N;i++){
    const a=nodes[i];
    for(let j=i+1;j<N;j++){
      const b=nodes[j];
      const need = a.r+b.r+17;   // 留出标签的位置，不只是点与点不碰
      let dx=b.x-a.x, dy=b.y-a.y, d=Math.hypot(dx,dy);
      if(d>=need) continue;
      if(d<0.01){ dx=(Math.random()-.5)*2; dy=(Math.random()-.5)*2; d=1; }
      const push=(need-d)/2, ux=dx/d, uy=dy/d;
      a.x-=ux*push; a.y-=uy*push; b.x+=ux*push; b.y+=uy*push;
    }
  }

  gaps.forEach(g=>{ g.vx+=(g.hx-g.x)*0.05*k; g.vy+=(g.hy-g.y)*0.05*k; });

  // ⑤ 阻尼 + 边界
  const pad = 40;
  nodes.forEach(n=>{
    n.vx*=0.70; n.vy*=0.70; n.x+=n.vx; n.y+=n.vy;
    n.x=Math.max(pad,Math.min(W-pad,n.x)); n.y=Math.max(pad,Math.min(H-pad,n.y));
  });
  gaps.forEach(g=>{ g.vx*=0.75; g.vy*=0.75; g.x+=g.vx; g.y+=g.vy; });
}

/* 悬空概念铺在最外环——它们是网络的边界，本就该在外围 */
function placeGaps(){
  const R = Math.min(W,H)*0.485;
  gaps.forEach((g,i)=>{
    const a = (i/Math.max(1,gaps.length))*Math.PI*2 + 0.4;
    g.hx = W/2 + Math.cos(a)*R*1.02;
    g.hy = H/2 + Math.sin(a)*R*1.02*0.80;
  });
}

/* ── 绘制 ─────────────────────────────────────────── */
function visible(n){
  if(filter && n.d!==filter) return false;
  if(query && !norm(n.t).includes(norm(query))) return false;
  return true;
}

let stars=null;
function makeStars(){                 // 极淡的背景星尘：给纵深，不抢数据
  if(stars && stars.w===W && stars.h===H) return;
  let seed=20261008;
  const rnd=()=>((seed=seed*1103515245+12345&0x7fffffff)/0x7fffffff);
  stars={w:W,h:H,pts:Array.from({length:Math.round(W*H/9000)},()=>({
    x:rnd()*W, y:rnd()*H, r:rnd()*0.9+0.25, a:rnd()*0.30+0.06 }))};
}
function draw(){
  ctx.setTransform(DPR,0,0,DPR,0,0);
  // 渐晕底
  const vg=ctx.createRadialGradient(W*0.52,H*0.5,0,W*0.52,H*0.5,Math.max(W,H)*0.72);
  vg.addColorStop(0,'#0d1418'); vg.addColorStop(0.55,'#0a0e11'); vg.addColorStop(1,'#06090b');
  ctx.fillStyle=vg; ctx.fillRect(0,0,W,H);
  // 星尘
  makeStars();
  stars.pts.forEach(p=>{
    ctx.globalAlpha=p.a; ctx.fillStyle='#cfe8e0';
    ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,7); ctx.fill();
  });
  ctx.globalAlpha=1;

  // 领域底盘
  doms.forEach(d=>{
    const A=domAnchor[d.id];
    const on = !filter || filter===d.id;
    const g = ctx.createRadialGradient(A.x,A.y,0,A.x,A.y,A.rad*1.9);
    g.addColorStop(0, on?'rgba(88,201,163,.10)':'rgba(88,201,163,.02)');
    g.addColorStop(1,'rgba(88,201,163,0)');
    ctx.fillStyle=g;
    ctx.beginPath(); ctx.arc(A.x,A.y,A.rad*1.9,0,7); ctx.fill();
    ctx.strokeStyle = on?'rgba(88,201,163,.09)':'rgba(88,201,163,.03)';
    ctx.lineWidth=1; ctx.beginPath(); ctx.arc(A.x,A.y,A.rad*1.5,0,7); ctx.stroke();
  });

  // 连线
  E.forEach(e=>{
    const a=nodes[e.a], b=nodes[e.b];
    const on = visible(a)&&visible(b);
    ctx.strokeStyle = e.cross
      ? (on?'rgba(201,164,76,.30)':'rgba(201,164,76,.05)')
      : (on?'rgba(88,201,163,.15)':'rgba(88,201,163,.035)');
    ctx.lineWidth = e.cross?1.15:0.7;
    ctx.beginPath();
    if(e.cross){                       // 跨领域走弧线，避免穿过中心
      const mx=(a.x+b.x)/2, my=(a.y+b.y)/2;
      const nx=-(b.y-a.y), ny=(b.x-a.x), L=Math.hypot(nx,ny)||1;
      const bow = Math.min(120, L*0.22);
      ctx.moveTo(a.x,a.y);
      ctx.quadraticCurveTo(mx+nx/L*bow, my+ny/L*bow, b.x,b.y);
    } else { ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); }
    ctx.stroke();
  });

  // 悬空概念
  gaps.forEach(g=>{
    const hot = hover && hover.gap===g;
    ctx.strokeStyle = hot?'#9df0cf':'rgba(58,74,77,.85)';
    ctx.lineWidth = hot?1.5:1;
    ctx.beginPath(); ctx.arc(g.x,g.y, hot?4:2.6, 0, 7); ctx.stroke();
  });

  // 节点
  const RAMP=D.ramp;
  nodes.forEach(n=>{
    const on = visible(n);
    const hot = hover && hover.node===n, chosen = sel===n;
    const col = RAMP[n.bin];
    ctx.globalAlpha = on?1:0.16;
    if(hot||chosen){
      ctx.beginPath(); ctx.arc(n.x,n.y,n.r+7,0,7);
      ctx.fillStyle = chosen?'rgba(157,240,207,.20)':'rgba(157,240,207,.11)';
      ctx.fill();
    }
    // 2px 表面色描边：重叠的星点靠它分开（marks 规范）
    ctx.beginPath(); ctx.arc(n.x,n.y,n.r+1.6,0,7);
    ctx.fillStyle = '#0a0d0f'; ctx.fill();
    if(n.bin>=2){                       // 枢纽带辉光，星等越高越亮
      ctx.shadowColor=col; ctx.shadowBlur=n.bin>=3?16:9;
    }
    ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,7);
    ctx.fillStyle = col; ctx.fill();
    ctx.shadowBlur=0;
    if(chosen){ ctx.strokeStyle='#9df0cf'; ctx.lineWidth=1.6; ctx.stroke(); }
    ctx.globalAlpha = 1;
  });

  // 标注：枢纽常显，选中/悬停必显
  ctx.textAlign='center'; ctx.textBaseline='top';
  ctx.lineJoin='round';
  // 先描一圈底色再填字：标签压在线条/星点上时，靠这圈黑边保住可读性
  const halo=(t,x,y,fill,size,weight)=>{
    ctx.font=(weight||400)+' '+size+'px "Noto Sans SC",sans-serif';
    ctx.lineWidth=Math.max(3, size*0.34);
    ctx.strokeStyle='rgba(6,9,11,.94)';
    ctx.strokeText(t,x,y);
    ctx.fillStyle=fill; ctx.fillText(t,x,y);
  };
  nodes.forEach(n=>{
    const on = visible(n);
    const must = hover&&hover.node===n || sel===n;
    // 只给枢纽常显标签——178 个标签全画出来只会糊成一片
    if(!(must || (on && n.bin>=3))) return;
    ctx.globalAlpha = on?1:0.22;
    const hot2 = must || n.bin>=3;
    halo(n.t, n.x, n.y+n.r+5,
         must?'#ffffff':(hot2?'#f4fffb':'rgba(232,242,238,.82)'),
         hot2?12.5:11.5, hot2?500:400);
    ctx.globalAlpha = 1;
  });
  gaps.forEach(g=>{
    if(!(hover&&hover.gap===g)) return;
    halo(g.t+' ?', g.x, g.y+8, '#d8fff0', 12, 500);
  });

  // 领域名
  doms.forEach(d=>{
    const A=domAnchor[d.id];
    const on = !filter || filter===d.id;
    const sp=d.name.replace(/([一-鿿])/g,'$1 ');   // 字距只加在中文字之间
    ctx.globalAlpha = on?1:0.28;
    halo(sp, A.x, A.y - A.rad - 26, on?'#e8f6f1':'rgba(232,246,241,.5)', 13.5, 500);
    ctx.globalAlpha = 1;
  });
}

/* ── 交互 ─────────────────────────────────────────── */
function pick(mx,my){
  let best=null, bd=1e9;
  nodes.forEach(n=>{
    if(!visible(n)) return;
    const d=Math.hypot(n.x-mx,n.y-my);
    if(d<n.r+9 && d<bd){ bd=d; best={node:n}; }
  });
  if(best) return best;
  gaps.forEach(g=>{
    const d=Math.hypot(g.x-mx,g.y-my);
    if(d<10 && d<bd){ bd=d; best={gap:g}; }
  });
  return best;
}

let dragging=false, moved=false;
cv.addEventListener('pointerdown',e=>{dragging=true;moved=false;cv.classList.add('drag');cv.setPointerCapture(e.pointerId)});
cv.addEventListener('pointermove',e=>{
  const r=cv.getBoundingClientRect(), mx=e.clientX-r.left, my=e.clientY-r.top;
  if(dragging){ if(Math.abs(e.movementX)+Math.abs(e.movementY)>1) moved=true; }
  const h=pick(mx,my);
  if(JSON.stringify(h&&(h.node?h.node.t:h.gap.t))!==JSON.stringify(hover&&(hover.node?hover.node.t:hover.gap.t))){
    hover=h; draw(); cv.style.cursor = h?'pointer':'grab';
  }
});
cv.addEventListener('pointerup',e=>{
  dragging=false; cv.classList.remove('drag');
  if(moved) return;
  const r=cv.getBoundingClientRect();
  const h=pick(e.clientX-r.left, e.clientY-r.top);
  sel = h&&h.node? h.node : null;
  showDetail(h);
});
cv.addEventListener('pointerleave',()=>{hover=null;draw()});

/* 详情 —— 正文是主角，链接是次要信息 */
function findNode(t){                       // 同名/包含都能找到
  const n0=norm(t);
  if(idxOf[n0]!=null) return nodes[idxOf[n0]];
  for(const k in idxOf){
    if(n0 && (n0.includes(k) || k.includes(n0))) return nodes[idxOf[k]];
  }
  return null;
}
function showDetail(h){
  const box=document.getElementById('det');
  if(!h){ box.classList.remove('on'); fit(); draw(); return; }
  if(h.gap){
    document.getElementById('dt').textContent = h.gap.t;
    document.getElementById('dm').innerHTML = '<em>悬空概念</em> · 被引用 ' + h.gap.n + ' 次，但还没有条目';
    document.getElementById('db').innerHTML =
      '<p class="none">这是知识网络的边界。被反复引用、却从没写下来过——'
      + '补一条，这张网就往外长一格。</p>';
    document.getElementById('dout').innerHTML=''; document.getElementById('din').innerHTML='';
    box.classList.add('on'); fit(); draw(); return;
  }
  const n=h.node;
  const dm=D.domains.find(x=>x.id===n.d);
  document.getElementById('dt').textContent = n.t;
  document.getElementById('dm').innerHTML =
    '<em>'+n.k+'</em> · '+(dm?dm.name:'')+' · 被引 <em>'+n.deg+'</em> 次';
  document.getElementById('db').innerHTML =
    n.h || '<p class="none">（这一条只有标题，正文还没写）</p>';
  // 正文里的 [[链接]] 可点
  document.querySelectorAll('#db a.wl').forEach(a=>{
    a.onclick=()=>{ const t=findNode(a.dataset.t);
      if(!t) return;                       // 指向悬空概念：先不动
      sel=t; showDetail({node:t}); draw(); };
  });
  const out = E.filter(e=>e.a===n.idx).map(e=>nodes[e.b]);
  const inn = E.filter(e=>e.b===n.idx).map(e=>nodes[e.a]);
  const li = a => a.length? a.map(x=>'<li data-t="'+x.t.replace(/"/g,'&quot;')+'">'+x.t+'</li>').join('')
                        : '<li class="none">—</li>';
  document.getElementById('dout').innerHTML = li(out);
  document.getElementById('din').innerHTML  = li(inn);
  box.classList.add('on');
  fit(); draw();                           // 给面板让出位置，图整体左移
}
document.getElementById('dx').onclick=()=>{
  sel=null; document.getElementById('det').classList.remove('on'); fit(); draw();
};
['dout','din'].forEach(id=>document.getElementById(id).addEventListener('click',e=>{
  const t=e.target.dataset.t; if(!t) return;
  const n2=findNode(t); if(!n2) return;
  sel=n2; showDetail({node:n2}); draw();
}));

/* 筛选 */
const chips=document.getElementById('chips');
D.domains.filter(d=>domCount[d.id]).forEach(d=>{
  const b=document.createElement('button');
  b.className='chip'; b.textContent=d.name; b.setAttribute('aria-pressed','false');
  b.onclick=()=>{
    filter = (filter===d.id)? null : d.id;
    [...chips.children].forEach(c=>c.setAttribute('aria-pressed','false'));
    if(filter) b.setAttribute('aria-pressed','true');
    draw();
  };
  chips.appendChild(b);
});
document.getElementById('q').addEventListener('input',e=>{query=e.target.value.trim();draw()});

/* 图例 */
const RAMP=D.ramp, LAB=['1–2 次','3–5 次','6–9 次','10+ 次'];
document.getElementById('ramp').innerHTML = RAMP.map((c,i)=>
  '<div><span class="dot" style="width:'+(7+i*2.6)+'px;height:'+(7+i*2.6)+'px;background:'+c+'"></span>'+LAB[i]+'</div>').join('');

/* ── 启动 ─────────────────────────────────────────── */

document.getElementById('stat').innerHTML =
  '<b>'+D.stats.nodes+'</b> 颗星<i>·</i><b>'+D.stats.links+'</b> 条连线<i>·</i>跨领域 <b>'
  +D.stats.cross+'</b> 条<i>·</i>悬空 <b>'+D.stats.gaps+'</b> 个';

/* 一切都声明完了，最后才启动 */
window.addEventListener('resize',resize);
resize();

/* 同步收敛 + 自适应缩放。
   不用 requestAnimationFrame 逐帧跑：无头截图与真实浏览器的帧时序不同，
   帧驱动会让布局变成"看运气"。星图本就该静止，一次算完最稳。 */
function settle(){
  const N = 620;
  for(let t=0;t<N;t++) step(1 - t/N);
}
/* 从原始坐标算一次适配，写进显示坐标。
   保留 raw，是为了让 fit 可重复调用而不累积缩放；领域锚点也必须一起变换，
   否则领域名与光晕会留在旧位置（踩过）。 */
function fit(){
  const narrow = W < 720;
  const open = document.getElementById('det').classList.contains('on');
  const padL = narrow ? 20 : 336;
  const padR = narrow ? 20 : (open ? Math.min(560, W*0.42) : 46);
  const padT = narrow ? 64 : 70,  padB = narrow ? 290 : 70;
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  raw.forEach(n=>{ x0=Math.min(x0,n.x-n.r); x1=Math.max(x1,n.x+n.r);
                   y0=Math.min(y0,n.y-n.r); y1=Math.max(y1,n.y+n.r); });
  const bw=Math.max(1,x1-x0), bh=Math.max(1,y1-y0);
  // 只缩不放：放大连同半径一起吹大，星点会变成互相压住的球（踩过）
  const s=Math.min((W-padL-padR)/bw, (H-padT-padB)/bh, 1.0);
  const ox=padL + ((W-padL-padR) - bw*s)/2 - x0*s;
  const oy=padT + ((H-padT-padB) - bh*s)/2 - y0*s;
  const all=[...nodes,...gaps];
  all.forEach((n,i)=>{ n.x = raw[i].x*s+ox; n.y = raw[i].y*s+oy;
                       n.r = Math.max(1.5, raw[i].r*s); });
  doms.forEach((d,i)=>{ const A=domAnchor[d.id];
    A.x = domRaw[i].x*s+ox; A.y = domRaw[i].y*s+oy; A.rad = domRaw[i].rad*s; });
}
function rebuild(){
  layout(); placeGaps(); settle();
  raw = [...nodes,...gaps].map(n=>({x:n.x,y:n.y,r:n.r||2}));
  domRaw = doms.map(d=>({x:domAnchor[d.id].x, y:domAnchor[d.id].y, rad:domAnchor[d.id].rad}));
  fit();
}

function resize(){
  DPR=Math.min(2,window.devicePixelRatio||1);
  W=window.innerWidth; H=window.innerHeight;
  cv.width=W*DPR; cv.height=H*DPR;
  cv.style.width=W+'px'; cv.style.height=H+'px';
  rebuild(); draw();
}
</script>
"""

if __name__ == "__main__":
    main()
