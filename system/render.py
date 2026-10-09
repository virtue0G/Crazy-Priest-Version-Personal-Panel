"""从数据库渲染面板 HTML。

这一层 A（技能式）与 B（独立应用）完全共用——将来套 Web 壳，这里照用。
"""
from pathlib import Path
from db import connect, REALMS, dao_marks

OUT = Path(__file__).parent.parent / "panel.html"

CSS = """
:root{--bg:#07090a;--panel:#0e1315;--panel2:#0b0f11;--line:#1d2729;--line2:#2c3c3e;
--ink:#dfe6e2;--mut:#7f8f8b;--dim:#4f5d5b;--jade:#58c9a3;--jadehi:#8fe6c4;
--blood:#c8433c;--gold:#c9a44c;--yuan:#6fb8d8;--serif:"Noto Serif SC",serif;
--sans:"Noto Sans SC","PingFang SC",sans-serif;--num:"Rajdhani",sans-serif}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-weight:300;
font-size:14px;line-height:1.75;background-image:radial-gradient(880px 420px at 50% -180px,#0e1a18 0,transparent 66%)}
.wrap{max-width:900px;margin:0 auto;padding:52px 28px 72px}
.eyebrow{font-family:var(--serif);font-size:11px;letter-spacing:.42em;color:var(--jade)}
.rule{height:1px;background:linear-gradient(90deg,transparent,var(--line2),transparent);margin:24px 0}
section{margin-top:46px}
.shead{display:flex;align-items:baseline;gap:12px;margin-bottom:16px}
.shead h2{font-family:var(--serif);font-weight:600;font-size:16px;letter-spacing:.16em}
.shead .hint{font-size:11.5px;color:var(--dim);margin-left:auto}
.title{text-align:center}
.sect-name{font-family:var(--serif);font-weight:900;font-size:32px;letter-spacing:.1em;
background:linear-gradient(180deg,#e8f5ef,#4fae8b);-webkit-background-clip:text;background-clip:text;color:transparent}
.axes{margin:20px auto 0;display:flex;justify-content:center;flex-wrap:wrap;max-width:660px}
.ax{flex:1 1 270px;padding:11px 16px;border:1px solid var(--line);background:#0b1010}
.ax:first-child{border-right:none}
.ax .k{font-size:10.5px;color:var(--dim);letter-spacing:.18em}
.ax .v{font-family:var(--serif);font-size:15px;margin-top:3px}
.ax .v b{color:var(--jadehi)}.ax .n{font-size:11px;color:var(--mut);margin-top:2px}
.apx{margin:10px auto 0;max-width:660px;padding:9px 14px;border:1px solid var(--line);border-left:2px solid var(--yuan);
background:#0a1114;font-size:12px;color:#b3bdb7;display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
.apx b{color:var(--yuan)}.apd{font-family:var(--num);color:var(--mut)}
.aph{margin-left:auto;font-size:10.5px;color:var(--dim)}
.dao{padding:15px 2px 14px;border-bottom:1px solid #151f1f}
.dao:last-child{border-bottom:none}
.dr1{display:flex;align-items:center;gap:10px}
.dn{font-family:var(--serif);font-weight:900;font-size:17px;letter-spacing:.1em;min-width:60px}
.dgu{font-family:var(--serif);font-size:12px;color:var(--jade)}
.dtag{font-size:9.5px;border:1px solid var(--line2);border-radius:20px;padding:0 6px;color:var(--dim)}
.dtag.dev{border-color:#5a4a1e;color:var(--gold)}
.ladder{margin-left:auto;display:flex;gap:5px}
.ladder i{width:14px;height:5px;border-radius:2px;background:#18211f}
.ladder i.on{background:linear-gradient(90deg,#2f8f6d,#8fe6c4)}
.dr-rank{font-family:var(--serif);font-size:13px;color:var(--mut);min-width:34px;text-align:right}
.dr2{display:flex;align-items:baseline;gap:12px;margin-top:6px}
.dline{font-family:var(--serif);font-size:13.5px;color:#b3bdb7}
.dmeta{margin-left:auto;font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
.dmeta b{color:var(--jade)}.dr3{margin-top:5px;font-size:11.5px;color:var(--dim)}
.dr3 b{color:var(--jade)}
.gu{border:1px solid var(--line);border-radius:12px;padding:13px 16px;background:var(--panel);margin-bottom:10px}
.gu.vital{border-color:#37564a}.gu.immortal{border-color:#4d4020}
.gu .row{display:flex;align-items:baseline;gap:12px}
.guname{font-family:var(--serif);font-weight:900;font-size:16px;letter-spacing:.08em}
.gudao{margin-left:auto;font-size:11px;color:var(--dim)}.gudao b{color:var(--jade)}
.gutag{float:right;font-size:10px;border:1px solid currentColor;border-radius:20px;padding:1px 8px;color:var(--gold)}
.moves{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.move{border:1px solid var(--line);border-radius:12px;padding:14px 15px;background:var(--panel2)}
.move.top{border-color:#6b5a24}.move.ready{border-color:#3d5a2f}
.move .mn{font-family:var(--serif);font-weight:900;font-size:15px}
.move .st{font-size:10px;border:1px solid currentColor;border-radius:20px;padding:0 7px;margin-left:7px;color:var(--gold)}
.move .mat{margin-top:8px;font-size:11.5px;color:var(--mut)}.move .mat b{color:var(--jade)}
.move .ms{font-size:12px;color:#bcc6c1;margin-top:7px}
.today{border:1px solid #2c4a3f;border-radius:14px;padding:18px 20px;background:linear-gradient(180deg,#0e1a16,#0a1013)}
.tname{font-family:var(--serif);font-weight:900;font-size:18px}
.t5{margin-top:12px;padding-top:11px;border-top:1px dashed #24352f;font-size:12.5px;color:#c2cec9}
.t5 b{color:var(--jade)}
.rec{margin-bottom:22px;padding:14px 16px;border:1px solid #24352f;border-radius:12px;background:#0a1013}
.rech{display:flex;gap:10px;align-items:baseline;margin-bottom:8px;font-family:var(--serif);font-size:14px}
.rec textarea{width:100%;background:#070d0f;border:1px solid var(--line);border-radius:8px;color:var(--ink);
padding:9px 11px;font-family:var(--sans);font-size:12.5px;font-weight:300;line-height:1.7;resize:vertical}
.rec textarea:focus{outline:none;border-color:var(--jade)}
.bar{display:flex;gap:12px;align-items:center;margin-top:9px;flex-wrap:wrap}
.bar button{background:linear-gradient(180deg,#2f8f6d,#226b52);color:#eafff7;border:none;border-radius:8px;
padding:7px 18px;font-family:var(--sans);font-size:12.5px;letter-spacing:.06em;cursor:pointer}
.bar button:hover{filter:brightness(1.12)}
.bar button .n{font-family:var(--num);font-weight:700}
.tip{font-size:11px;color:var(--dim)}
.ev input[type=checkbox]{accent-color:var(--jade);margin-right:6px;vertical-align:middle}
details{margin-top:4px}
summary{cursor:pointer;list-style:none;display:flex;align-items:baseline;gap:12px;
padding:9px 2px;border-bottom:1px solid #151f1f}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";color:var(--dim);font-size:11px;flex:none}
details[open] summary::before{content:"▾";color:var(--jade)}
summary:hover .sh2{color:var(--jadehi)}
.sh2{font-family:var(--serif);font-weight:600;font-size:14px;letter-spacing:.14em;color:#8f9d98}
.shint{margin-left:auto;font-size:11px;color:var(--dim);text-align:right}
.dbody{padding:12px 2px 0}
.ld{margin-bottom:14px;padding:12px 15px;border:1px solid var(--line);border-radius:11px;background:var(--panel2)}
.ldh{display:flex;align-items:baseline;gap:10px;margin-bottom:7px}
.ldh .dmeta{margin-left:auto;font-size:11px;color:var(--dim)}
.ldh .dmeta b{color:var(--jade)}
.lr{list-style:none}
.lr li{display:flex;gap:10px;padding:2.5px 0;font-size:12px;align-items:baseline}
.lr .rl{font-family:var(--serif);min-width:74px;font-size:11.5px;color:var(--dim)}
.lr .rt{color:#3f4b49}
.lr li.done .rt{color:#6d7a76}.lr li.done .rl{color:#4d6b5e}
.lr li.next .rt{color:#d8e6df}.lr li.next .rl{color:var(--jade);font-weight:600}
.lr li.next .rt::before{content:"▸ ";color:var(--jade)}
.ev{list-style:none;font-size:12px;color:#a9b3ad}
.ev li{padding:3px 0;border-bottom:1px dashed #161e1e}
.ev .d{font-family:var(--num);color:var(--gold);margin-right:7px}
footer{margin-top:40px;padding-top:16px;border-top:1px solid #151f1f;color:var(--dim);font-size:11px;line-height:2;text-align:center}
"""


CN = "零一二三四五六七八九十"


def cn_num(n: int) -> str:
    return CN[n] if n <= 10 else str(n)


def ladder(idx: int) -> str:
    return "".join(f'<i class="{"on" if i <= idx else ""}"></i>' for i in range(7))


def pick_today(con):
    """今日一炼：从数据里选——最饿的、且写了日常练法的凡蛊。

    不硬编码任何文案，因此永远不会与数据脱节。
    """
    return con.execute("""
        SELECT * FROM gu
        WHERE kind='凡' AND is_vital=0 AND practice IS NOT NULL
        ORDER BY CASE state WHEN '濒死' THEN 0 WHEN '饥饿' THEN 1
                           WHEN '微饥' THEN 2 ELSE 3 END, id
        LIMIT 1""").fetchone()


def section(title: str, hint: str = "", body: str = "", folded: bool = False) -> str:
    """一节。

    folded=True → 默认收起，只露一行「摘要」；点开才看细节。

    这是刻意的：**面板默认只回答「我现在该干什么」，其余信息在该出现时才出现。**
    一股脑摊开的结果是——真正要你做的那件事，会被四十行参考信息淹掉。
    hint 就是那一行摘要，必须自带结论（几个、最要紧的是哪个），
    否则收起来等于藏起来。
    """
    if not folded:
        return (f'<section><div class="shead"><h2>{title}</h2>'
                f'<span class="hint">{hint}</span></div>{body}</section>')
    return (f'<section><details><summary><span class="sh2">{title}</span>'
            f'<span class="shint">{hint}</span></summary><div class="dbody">{body}</div>'
            f'</details></section>')


def gu_daos(con, gu_id):
    return [r["name"] for r in con.execute(
        "SELECT d.name FROM gu_dao gd JOIN daos d ON d.id=gd.dao_id WHERE gd.gu_id=?", (gu_id,))]


def render(web: bool = False):
    """web=True 时注入可交互的控件（记录框、确认勾选），供 web.py 使用。

    页面正文完全一致——网页壳只是多了一层可点的壳，不改事实层。
    """
    con = connect()
    daos = con.execute("SELECT * FROM daos WHERE active=1").fetchall()
    rows = sorted(((d, dao_marks(con, d["id"], confirmed=1)) for d in daos), key=lambda x: -x[1])
    pending_marks = {d["name"]: dao_marks(con, d["id"], confirmed=0) for d in daos}

    gu_by_dao = {}
    for g in con.execute("SELECT * FROM gu ORDER BY tier, id"):
        ds = [r["dao_id"] for r in con.execute("SELECT dao_id FROM gu_dao WHERE gu_id=?", (g["id"],))]
        gu_by_dao[g["id"]] = ds

    parts = [f'<title>问道 · 修行面板</title><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;900&family=Noto+Sans+SC:wght@300;400;500&family=Rajdhani:wght@500;700&display=swap"><style>{CSS}</style><div class="wrap">']

    # 网页壳的顶栏：记录框（写进 data/，等 AI 抽取）
    if web:
        inbox = Path(__file__).parent.parent / "data" / "收件箱.md"
        n_inbox = 0
        if inbox.exists():
            n_inbox = sum(1 for l in inbox.read_text(encoding="utf-8").splitlines() if l.strip())
        parts.append(f'''<form class="rec" method="post" action="/record">
<div class="rech"><b>随手记</b><span class="tip">写在这里 → 存进 data/收件箱.md → 对我说「跑今天的」，我再抽取</span></div>
<textarea name="text" rows="3" placeholder="今天做了什么、想到了什么、卡在哪……不必讲究格式"></textarea>
<div class="bar"><button type="submit">存下</button>
<span class="tip">收件箱现有 {n_inbox} 行待抽取</span></div></form>''')

    # 称号 —— 全部从库里算，不硬编码
    prof = {r["k"]: r["v"] for r in con.execute("SELECT * FROM profile")}
    cult, cap = prof.get("cultivation", "—"), prof.get("capacity", "—")
    main = next((d for d in daos if d["layer"] == "主修"), rows[0][0])
    realms = sorted({REALMS[d["realm_index"]] for d in daos})
    realm_txt = realms[0] if len(realms) == 1 else " / ".join(realms)
    parts.append(f'''<div class="title"><div class="eyebrow">蛊 师 位 阶</div>
<div class="sect-name">{main["name"]} · {cult}蛊师</div>
<div class="axes">
<div class="ax"><div class="k">修 为 · 能 不 能</div><div class="v">{cult} · <b>{cap}</b></div><div class="n">精力 · 时间 · 空窍容量</div></div>
<div class="ax"><div class="k">道 境 · 懂 不 懂</div><div class="v">{cn_num(len(daos))}道皆 <b>{realm_txt}</b></div><div class="n">境界由「达成之事」证明，不可自评</div></div>
</div></div>''')
    # 空窍读数 —— 带日期，自证是「截至某日」的一次自述，不冒充当下
    ap = con.execute("SELECT * FROM aperture ORDER BY date DESC LIMIT 1").fetchone()
    if ap:
        parts.append(f'''<div class="apx"><span class="apd">{ap["date"]}</span>
真元 <b>{ap["essence_pct"]}%</b> · {ap["mood_text"]} · {ap["energy_note"]}
<span class="aph">最近一次自述读数</span></div>''')
    parts.append('<div class="rule"></div>')

    # 今日一炼 —— 由「最饿的那只蛊」推出，文案全自动
    gu = pick_today(con)
    ds = gu_daos(con, gu["id"])
    parts.append(f'''<section style="margin-top:0"><div class="shead"><h2>今日一炼</h2><span class="hint">最小启动 · 放早上</span></div>
<div class="today"><div class="tname">{gu["name"]} · {gu["practice"]}</div>
<div class="t5"><b>5 分钟版</b>：把这件事缩到 5 分钟也算完成——低状态日就做这一版。<br>
为何先喂它：<b>{gu["name"]}已「{gu["state"]}」</b>，它相关之道为 {'、'.join(ds)}，是眼下最饿的一只。</div></div></section>''')

    # 诸道
    parts.append('<section><div class="shead"><h2>诸道 · 境界与道痕</h2>'
                 '<span class="hint">普通 → 大师 → 宗师 → 大宗师 → 准无上 → 无上 → 道主</span></div>')
    for d, mark in rows:
        gu_names = " · ".join(
            g["name"] for g in con.execute("SELECT * FROM gu ORDER BY tier,id")
            if d["id"] in gu_by_dao[g["id"]])
        tag = '<span class="dtag dev">复合衍生</span>' if d["origin"] == "衍生" else ""
        # 下一级的达成事件由境界推出；已至道主则标「已极」
        ni = d["realm_index"] + 1
        if ni < len(REALMS):
            rung = con.execute("SELECT event_desc FROM proof_ladder WHERE dao_id=? AND to_realm_index=?",
                               (d["id"], ni)).fetchone()
            proof = f'{REALMS[ni]}：{rung["event_desc"]}' if rung else "—"
        else:
            proof = "已至极境"
        parts.append(f'''<div class="dao"><div class="dr1"><span class="dn">{d["name"]}</span>{tag}
<span class="dgu">{gu_names or "—"}</span>
<span class="ladder">{ladder(d["realm_index"])}</span>
<span class="dr-rank">{REALMS[d["realm_index"]]}</span></div>
<div class="dr2"><span class="dline">{d["domain"]}</span>
<span class="dmeta">道痕 <b>~{mark}</b></span></div>
<div class="dr3">下一级 · <b>{proof}</b></div></div>''')
    parts.append("</section>")

    # 晋升阶梯 —— 收起。下一级已在「诸道」里，全路 48 级是想看时才看的东西
    ladder_body = []
    for d, mark in rows:
        rungs = con.execute(
            "SELECT to_realm_index, event_desc FROM proof_ladder WHERE dao_id=? ORDER BY to_realm_index",
            (d["id"],)).fetchall()
        cur = d["realm_index"]
        rows_html = []
        for r in rungs:
            tri = r["to_realm_index"]
            state = "done" if tri <= cur else "next" if tri == cur + 1 else "far"
            rows_html.append(f'<li class="{state}"><span class="rl">{REALMS[tri]}</span>'
                             f'<span class="rt">{r["event_desc"]}</span></li>')
        ladder_body.append(f'<div class="ld"><div class="ldh"><span class="dn">{d["name"]}</span>'
                           f'<span class="dmeta">道痕 <b>~{mark}</b> · 现 {REALMS[cur]}</span></div>'
                           f'<ul class="lr">{"".join(rows_html)}</ul></div>')
    parts.append(section(
        "晋升阶梯",
        f"{len(rows)} 道 × 6 级 · 下一级见上表 · 想看全路时展开",
        "".join(ladder_body), folded=True))

    # 愿望 —— 想做但没做。0 道痕，但它记的是「缺口」，不是「已有」
    wishes = con.execute("SELECT * FROM wishes ORDER BY ts DESC").fetchall()
    if wishes:
        wb = ['<ul class="ev">']
        for w in wishes:
            wb.append(f'<li><span class="d">{w["ts"] or "—"}</span>{w["text"]}'
                      f'<span class="d" style="margin-left:8px">［愿望 · {w["note"]}］</span></li>')
        wb.append("</ul>")
        # 收起，但摘要里说清「有几条、最近一条是什么」——收起不等于藏起来
        parts.append(section(
            "记下的缺口",
            f"{len(wishes)} 条想做没做 · 最近：{wishes[0]['text'][:18]}…",
            "".join(wb), folded=True))

    # 待确认（AI 提议、尚未经用户确认的证据）
    pend = con.execute(
        "SELECT * FROM evidence WHERE confirmed=0 ORDER BY COALESCE(ts,'') DESC").fetchall()
    if pend:
        total = sum(pending_marks.values())
        parts.append(f'<section><div class="shead"><h2>待你确认</h2>'
                     f'<span class="hint">{len(pend)} 条 · 合计 {total:g} 道痕（确认后才计入）</span></div>')
        if web:
            parts.append('<form method="post" action="/confirm"><ul class="ev">')
        else:
            parts.append('<ul class="ev">')
        for e in pend:
            alloc = " · ".join(f'{r["name"]} {r["w"]:g}' for r in con.execute(
                "SELECT d.name, ed.weight w FROM evidence_dao ed JOIN daos d ON d.id=ed.dao_id "
                "WHERE ed.evidence_id=?", (e["id"],)))
            box = (f'<input type="checkbox" name="id" value="{e["id"]}" checked> ' if web else "")
            parts.append(f'<li>{box}<span class="d">{e["ts"] or "—"}</span>{e["text"][:90]}'
                         f'<span class="d" style="margin-left:8px">［{e["source_type"]} · {alloc}］</span></li>')
        parts.append("</ul>")
        if web:
            parts.append('<div class="bar"><button type="submit">确认勾选的 '
                         f'<span class="n">{len(pend)}</span> 条</button>'
                         '<span class="tip">取消勾选 = 这条先不计入 · 确认后道痕立刻更新</span></div></form>')
        parts.append("</section>")

    # 所养之蛊 —— 只把「饿着的」摆出来，饱食的收起。
    # 天天列一遍九只蛊没有意义：不饿的蛊今天不需要你关心。
    def gu_html(g):
        ds = " / ".join(r["name"] for r in con.execute(
            "SELECT d.name FROM gu_dao gd JOIN daos d ON d.id=gd.dao_id WHERE gd.gu_id=?", (g["id"],)))
        tag = ('<span class="gutag">本 命 蛊</span>' if g["is_vital"]
               else '<span class="gutag">仙 蛊 · 在 炼</span>' if g["kind"] == "仙" else "")
        cls = "vital" if g["is_vital"] else "immortal" if g["kind"] == "仙" else ""
        return (f'<div class="gu {cls}">{tag}<div class="row"><span class="guname">{g["name"]}</span>'
                f'<span class="gudao">相关 · <b>{ds or "合炼而成"}</b></span></div></div>')

    all_gu = con.execute("SELECT * FROM gu ORDER BY is_vital DESC, tier, id").fetchall()
    hungry = [g for g in all_gu if g["state"] in ("濒死", "饥饿", "微饥")]
    sated = [g for g in all_gu if g not in hungry]
    gb = "".join(gu_html(g) for g in hungry)
    if sated:
        gb += (f'<details><summary><span class="sh2">其余 {len(sated)} 只 · 饱食</span>'
               f'<span class="shint">今天不必管</span></summary><div class="dbody">'
               + "".join(gu_html(g) for g in sated) + "</div></details>")
    parts.append(section(
        "所养之蛊",
        f"{len(hungry)} 只饿着 · " + "、".join(f'{g["name"]}{g["state"]}' for g in hungry[:3])
        if hungry else f"{len(all_gu)} 只皆饱食",
        gb))

    # 杀招 —— 只亮首选那一记，其余收起。
    # 理由：今日一炼已经给了「今天做哪一件」。四记杀招并排，等于又给四个方向，
    # 而用户的瓶颈恰恰是「懂却做不动」——方向多了只会更不动。
    def move_html(m, cls):
        mats = con.execute(
            "SELECT g.name, g.state FROM killer_move_gu mg JOIN gu g ON g.id=mg.gu_id "
            "WHERE mg.move_id=? ORDER BY CASE g.state WHEN '濒死' THEN 0 WHEN '饥饿' THEN 1 "
            "WHEN '微饥' THEN 2 ELSE 3 END, g.id", (m["id"],)).fetchall()
        fed = " · ".join(
            f'<b>{r["name"]}「{r["state"]}」</b>' if r["state"] in ("濒死", "饥饿", "微饥")
            else f'{r["name"]}「{r["state"]}」' for r in mats)
        return (f'<div class="move {cls}"><div class="mn">{m["name"]}'
                f'<span class="st">{m["status"]}</span></div>'
                f'<div class="mat">材料 · <b>{m["materials"]}</b></div><div class="ms">{m["note"]}</div>'
                f'<div class="mat" style="margin-top:6px">现况 · {fed}</div></div>')

    moves = con.execute("SELECT * FROM killer_moves ORDER BY seq").fetchall()
    top, rest = moves[:1], moves[1:]
    parts.append('<section><div class="shead"><h2>可炼之杀招</h2>'
                 '<span class="hint">兴趣优先于成本 · 首选一记，其余收起</span></div>'
                 '<div class="moves">' + "".join(move_html(m, "top") for m in top) + '</div>')
    if rest:
        inner = '<div class="moves">' + "".join(move_html(m, "") for m in rest) + "</div>"
        parts.append(section("其余杀招", f"{len(rest)} 记 · 想做别的时再看", inner, folded=True))
    parts.append("</section>")

    # 道痕明细（可溯源）—— 收起。它是审计线索，不是每天要看的
    n_ok = con.execute("SELECT COUNT(*) c FROM evidence WHERE confirmed=1").fetchone()["c"]
    latest = con.execute("SELECT ts FROM evidence WHERE confirmed=1 AND ts IS NOT NULL "
                         "ORDER BY ts DESC LIMIT 1").fetchone()
    eb = ['<ul class="ev">']
    for e in con.execute("SELECT * FROM evidence WHERE confirmed=1 ORDER BY COALESCE(ts,'') DESC LIMIT 12"):
        alloc = " · ".join(f'{r["name"]} {r["w"]:g}' for r in con.execute(
            "SELECT d.name, ed.weight w FROM evidence_dao ed JOIN daos d ON d.id=ed.dao_id "
            "WHERE ed.evidence_id=?", (e["id"],)))
        eb.append(f'<li><span class="d">{e["ts"] or "—"}</span>{e["text"]}'
                  f'<span class="d" style="margin-left:8px">［{alloc}］</span></li>')
    eb.append("</ul>")
    parts.append(section(
        "道痕明细",
        f"共 {n_ok} 条 · 最近 {latest['ts'] if latest else '—'} · 每条可溯源（此处列最近 12 条）",
        "".join(eb), folded=True))

    parts.append('<footer>本页由 system/render.py 从 growth.db 生成 · 数据来自真实记录与验证<br>'
                 '道痕宽，境界严：道痕记录你走过的路（含别人带着你走的），境界只认你自己打出来的。</footer></div>')

    html = "\n".join(parts)
    OUT.write_text(html, encoding="utf-8")
    print(f"✓ 已生成 {OUT}  ({len(html):,} 字符)")
    return OUT


if __name__ == "__main__":
    render()
