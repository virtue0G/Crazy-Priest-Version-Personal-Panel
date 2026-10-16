"""入口 —— 一条命令跑完整条流水线。

日常只有一条：

    python run.py           # 跑今天：重灌 → 抽新证据 → 出面板 → 自检 → 打印该看的几行
                            # （不带参数就是它。原来默认是 render，等于跑完数据不看结论）

随手记与自述（都能省 —— 心力不记也会按记录自己推）：

    python run.py 记 "今天调研了投手运营"    # 追加到 data/task.md 的当天段落
    python run.py 心力 12 周 无波 稳        # 记一条自述读数（不记 → 面板推一个下限）

其余（中文别名与英文等价：记/跑/看/检/面/炼/升/确认/测/建）：

    python run.py init      # 建库 + 灌已验证数据 + 出面板（第一次跑）
    python run.py render    # 只重新渲染面板（数据变了之后）
    python run.py rebuild   # 重置 → 灌数据 → 追加新证据 → 出面板
    python run.py check     # 完整性自检：跑一遍并核对信息无断链
    python run.py status    # 查看当前道痕与蛊的状态
    python run.py selftest  # 回归测试：改数据，面板必须跟着变
                            # （rebuild 结尾会自动跑一遍 check，跑通才算跑通）
    python run.py confirm   # 确认全部待确认证据（须用户授权）
    python run.py confirm 14 15   # 确认除 14、15 之外的全部
    python run.py feed 人言蛊    # 炼过一次 —— 记下日期，这只蛊的饥饱由数据推出来
    python run.py promote   # 看各道的下一级门槛
    python run.py promote 星道 "写下判断并写明证伪条件"   # 晋升：由「达成事件」触发
    python run.py web       # 起本地网页面板
"""
import sys
from datetime import date as _d
from pathlib import Path
from db import connect, REALMS, dao_marks, heart_reading, record_heart

PANEL = Path(__file__).parent.parent / "panel.html"
TASKLOG = Path(__file__).parent.parent / "data" / "task.md"

# 面板上「必须由数据算出」的字段。每项：([改数据的 SQL…], 期望改后出现的串, 说明)
# 若某天有人把这些值写死回模板，selftest 会红。
# 注意「今日一炼」要两条：只把机关蛊设为饥饿还不够——人言蛊是濒死，排位仍压它一头。
CASES = [
    (["UPDATE profile SET v='九转·测试' WHERE k='cultivation'"],
     "九转·测试", "修为轴 ← profile"),
    (["UPDATE gu SET state='饱食' WHERE name='人言蛊'",
      "UPDATE gu SET state='饥饿' WHERE name='机关蛊'"],
     "机关蛊 · 写一个小脚本解决一个重复动作", "今日一炼 ← 最饿的蛊"),
    (["UPDATE daos SET realm_index=1 WHERE name='律道'"],
     "下一级 · <b>宗师：", "下一级门槛 ← 当前境界"),
    (["UPDATE gu SET state='饥饿' WHERE name='铺路蛊'"],
     "铺路蛊「饥饿」", "杀招现况 ← 蛊的饥饱"),
    # ↓ 这两条是为一个真发生过的 bug 补的：当时的 `pick_today` 只在「写了练法的」里面排，
    #   却把「最饿」写死在文案里 —— 于是准绳蛊（真·最饿，但没写练法）一饿，
    #   面板就说出「火候蛊已『饱食』……是眼下最饿的一只」这种自己打自己的话。
    #   旧的 4 条用例**全过**，因为它们从没让「最饿的那只」缺过练法。
    (["UPDATE gu SET state='饥饿' WHERE name='准绳蛊'"],   # 准绳蛊恰好没写 practice
     "准绳蛊「饥饿」，但它还没定练法", "今日一炼 ← 最饿的那只没练法，要说出来"),
    (["UPDATE gu SET state='饱食' WHERE kind='凡'"],
     "只凡蛊眼下皆饱食", "今日一炼 ← 全饱食时不谎称「最饿」"),
]


def selftest():
    """改数据 → 面板必须跟着变。变了才算「文案从数据派生」。"""
    import render
    con = connect()
    backup = {
        "profile": list(con.execute("SELECT * FROM profile")),
        "gu": list(con.execute("SELECT * FROM gu")),
        "daos": list(con.execute("SELECT * FROM daos")),
    }
    ok = 0
    try:
        for sqls, expect, label in CASES:
            for sql in sqls:
                con.execute(sql)
            con.commit()
            render.render()
            html = PANEL.read_text(encoding="utf-8")
            hit = expect in html
            print(f"  {'✓' if hit else '✗'} {label:<22} {'跟随数据' if hit else f'未跟随！期望出现「{expect}」'}")
            ok += hit
            # 立刻还原这一项，避免用例之间互相污染
            for t, rows in backup.items():
                con.execute(f"DELETE FROM {t}")
                if rows:
                    cols = rows[0].keys()
                    con.executemany(
                        f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                        [tuple(r) for r in rows])
            con.commit()
    finally:
        for t, rows in backup.items():
            con.execute(f"DELETE FROM {t}")
            if rows:
                cols = rows[0].keys()
                con.executemany(
                    f"INSERT INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                    [tuple(r) for r in rows])
        con.commit()
    print(f"\n{'✓ 全部通过' if ok == len(CASES) else '✗ 有未通过项'}：{ok}/{len(CASES)}")
    return ok == len(CASES)


def status():
    con = connect()
    # 两列分开：面板只认「已确认」，待确认的要让用户看见它还没算进去
    print("道　　　　已确认   待确认   境界")
    print("─" * 38)
    rows = sorted(((d,
                    dao_marks(con, d["id"], confirmed=1),
                    dao_marks(con, d["id"], confirmed=0))
                   for d in con.execute("SELECT * FROM daos WHERE active=1")),
                  key=lambda x: -x[1])
    pend_total = 0.0
    for d, m, p in rows:
        pend_total += p
        print(f"{d['name']:<8}{m:>7}{p:>9}   {REALMS[d['realm_index']]}")
    n_pend = con.execute("SELECT COUNT(*) c FROM evidence WHERE confirmed=0").fetchone()["c"]
    if n_pend:
        print(f"\n　待确认 {n_pend} 条 · 合计 {pend_total:g} 道痕（确认后才进面板）")
    print()
    print("蛊　　　　　状态　　　相关之道")
    print("─" * 40)
    for g in con.execute("SELECT * FROM gu ORDER BY tier, id"):
        ds = " / ".join(r["name"] for r in con.execute(
            "SELECT d.name FROM gu_dao gd JOIN daos d ON d.id=gd.dao_id WHERE gd.gu_id=?", (g["id"],)))
        flag = "★本命" if g["is_vital"] else ""
        print(f"{g['name']:<9}{g['state']:<7}{ds or '（合炼而成）'} {flag}")


def check():
    """完整性自检：跑一遍并核对「信息读得完整、没有断链」。"""
    from db import connect, dao_marks, REALMS
    con = connect()
    bad = []

    def q(sql, *a):
        return con.execute(sql, a).fetchone()["c"]

    tests = [
        ("无归属的证据", q("SELECT COUNT(*) c FROM evidence e WHERE NOT EXISTS"
                          "(SELECT 1 FROM evidence_dao ed WHERE ed.evidence_id=e.id)")),
        ("孤儿归属", q("SELECT COUNT(*) c FROM evidence_dao ed WHERE NOT EXISTS"
                      "(SELECT 1 FROM evidence e WHERE e.id=ed.evidence_id)")),
        ("蛊指向不存在的道", q("SELECT COUNT(*) c FROM gu_dao gd WHERE NOT EXISTS"
                            "(SELECT 1 FROM daos d WHERE d.id=gd.dao_id)")),
        ("杀招指向不存在的蛊", q("SELECT COUNT(*) c FROM killer_move_gu mg WHERE NOT EXISTS"
                              "(SELECT 1 FROM gu g WHERE g.id=mg.gu_id)")),
        ("阶梯不完整的道", sum(1 for d in con.execute("SELECT id FROM daos WHERE active=1")
                          if [r["to_realm_index"] for r in con.execute(
                              "SELECT to_realm_index FROM proof_ladder WHERE dao_id=? ORDER BY 1",
                              (d["id"],))] != [1, 2, 3, 4, 5, 6])),
        # 境界不另存真相：realm_index 必须等于晋升流水的最后一笔。
        # 两者一旦各自漂移，面板上就会写着「大师」而找不到是哪件事升的——
        # 这正是 rebuild 抹掉 realms_log 之后的样子。
        ("境界与晋升流水不符", q("SELECT COUNT(*) c FROM daos d WHERE d.realm_index <> "
                            "COALESCE((SELECT MAX(r.to_realm) FROM realms_log r "
                            "WHERE r.dao_id=d.id), 0)")),
    ]
    print("═══ 完整性 ═══")
    for name, n in tests:
        print(f"  {'✓' if n == 0 else '✗'} {name:<22}{n}")
        if n:
            bad.append(name)

    tot = con.execute("SELECT SUM(weight) s FROM evidence_dao ed JOIN evidence e "
                      "ON e.id=ed.evidence_id WHERE e.confirmed=1").fetchone()["s"] or 0
    # digits=None：这里要的是恒等式，不是显示值。每道先舍入再相加会凭空造出误差。
    per = sum(dao_marks(con, d["id"], confirmed=1, digits=None)
              for d in con.execute("SELECT id FROM daos WHERE active=1"))
    ok = abs(tot - per) < 1e-6
    print(f"  {'✓' if ok else '✗'} 道痕守恒 逐条={tot:g} 逐道={per:g}")
    if not ok:
        bad.append("道痕不守恒")

    print("\n═══ 数字 ═══")
    print(f"  证据 {q('SELECT COUNT(*) c FROM evidence')}"
          f" · 已确认 {q('SELECT COUNT(*) c FROM evidence WHERE confirmed=1')}"
          f" · 愿望 {q('SELECT COUNT(*) c FROM wishes')}"
          f" · 蛊 {q('SELECT COUNT(*) c FROM gu')}"
          f" · 道 {q('SELECT COUNT(*) c FROM daos')}"
          f" · 阶梯 {q('SELECT COUNT(*) c FROM proof_ladder')} 级")

    print("\n═══ 各道 ═══")
    rows = sorted(((d, dao_marks(con, d["id"], confirmed=1)) for d in con.execute("SELECT * FROM daos")),
                  key=lambda x: -x[1])
    for d, m in rows:
        r = con.execute("SELECT event_desc FROM proof_ladder WHERE dao_id=? AND to_realm_index=?",
                        (d["id"], d["realm_index"] + 1)).fetchone()
        nxt = r["event_desc"] if r else "已至极境"
        print(f"  {d['name']:<5}{m:>6}  {REALMS[d['realm_index']]:<4} 下一级：{nxt}")

    # 面板结构：标签必须配对。
    # 为什么值得单独查：漏一个 </div> 不会报错、页面也照常显示，
    # 但浏览器会把后面的元素一路吞进错误的父节点里，样式悄悄错位——
    # 文本 dump 完全看不出来。这个 bug 真的发生过一次（称号块漏了 </div>）。
    import re
    if PANEL.exists():
        html = PANEL.read_text(encoding="utf-8")
        print("\n═══ 面板结构 ═══")
        unbalanced = []
        for tag in ("section", "details", "summary", "ul", "li", "div", "span"):
            o = len(re.findall(rf"<{tag}[\s>]", html))
            c = len(re.findall(rf"</{tag}>", html))
            if o != c:
                unbalanced.append(f"{tag} {o}/{c}")
        if unbalanced:
            bad.append("标签不配对")
            print(f"  ✗ 标签不配对：{'、'.join(unbalanced)}")
        else:
            print(f"  ✓ 标签全部配对（{len(html):,} 字符）")

    print(f"\n  {'✓ 全部通过' if not bad else '⚠ 有问题：' + '、'.join(bad)}")
    return not bad


def rebuild() -> bool:
    """重置 → 灌已验证数据 → 追加新证据（待确认）→ 出面板 → 自检。

    ★ 关键：重建会清空 evidence 表，但**确认是用户做的决定，不是种子数据**。
      重建一次就抹掉，等于让人白确认——这件事真的发生过（17 条被抹）。
      故先快照，重建后再贴回去。

      四套快照 + 一套晋升流水，各管一半：
        · (ts, text) —— 手写证据。正文不会自己变，够用。
        · ext_key    —— 外部回执。**正文会随数据刷新而变**（指标数字动了 text 就变了），
                        (ts, text) 立刻失配、掉回「待你确认」，变成天天重签。
                        ext_key 不随正文漂移，由它兜住。
        · 分配 / fed_at / realms_log —— 都是「人的决定」。
      手写记录的分配**不**快照：它以 baseline.json 为单一真相源，两处都改会打架。
    """
    import seed, ingest, render
    from db import (apply_confirmed_keys, apply_confirmations, apply_external_alloc,
                    apply_gu_fed, apply_realms, refresh_gu_states,
                    snapshot_confirmed_keys, snapshot_confirmations,
                    snapshot_external_alloc, snapshot_gu_fed, snapshot_realms)
    con = connect()
    prior = snapshot_confirmations(con)
    prior_keys = snapshot_confirmed_keys(con)
    prior_alloc = snapshot_external_alloc(con)
    prior_fed = snapshot_gu_fed(con)
    prior_realms = snapshot_realms(con)
    n_conf_before = con.execute(
        "SELECT COUNT(*) c FROM evidence WHERE confirmed=1").fetchone()["c"]
    seed.run()
    ingest.run()
    apply_confirmations(con, prior)
    apply_confirmed_keys(con, prior_keys)
    apply_external_alloc(con, prior_alloc)
    apply_gu_fed(con, prior_fed)
    n_realms = apply_realms(con, prior_realms)
    refresh_gu_states(con)          # 日子过一天，饿着的蛊就该掉一档
    render.render()
    if prior_realms:
        # 晋升和确认一样是「人的决定」——贴回来几条要说，一条没贴回来更要说
        print(f"✓ 已贴回 {n_realms} 级晋升"
              + ("" if n_realms == len(prior_realms)
                 else f"，⚠ 有 {len(prior_realms) - n_realms} 级因那道已不存在而失效"))
    if prior or prior_keys:
        # 真正要盯的不是「贴回几条」，而是「有没有哪条确认找不到它的证据了」——
        # 那才是被重建弄丢的用户决定。
        #
        # 报数直接数前后条数，**不要把两个集合的长度相加**：
        # 外部条目同时出现在 (ts,text) 集合和 ext_key 集合里，相加等于把它算两遍
        # （曾因此报出 71，而库里其实只有 68 条）。
        n_conf_after = con.execute(
            "SELECT COUNT(*) c FROM evidence WHERE confirmed=1").fetchone()["c"]
        live = {(r["ts"], r["text"]) for r in con.execute("SELECT ts, text FROM evidence")}
        live_keys = {r["ext_key"] for r in con.execute(
            "SELECT ext_key FROM evidence WHERE ext_key IS NOT NULL")}
        lost = (prior - live) | (prior_keys - live_keys)
        print(f"✓ 已确认 {n_conf_before} 条 → 重建后 {n_conf_after} 条"
              + (f"，⚠ {len(lost)} 条因原文已不存在而失效" if lost else "（重建不抹人的决定）"))
    if prior_alloc:
        print(f"✓ 外部条目上你调过的 {len(prior_alloc)} 组分配已贴回")
    # 跑通才算跑通：重建完自动核对一遍。道痕守恒、标签配对这类问题人眼看不出，
    # 但一旦坏了，页面会照常显示——所以不能靠"看着没问题"。
    print()
    return check()


def brief():
    """跑完之后，只打印**你现在该看的那几行**。

    用户 2026-10-16：「顺手的意思就是越简单越好，尽量不要让用户有多余的动作和操作。」
    所以日常只有一条命令 `python run.py`，它自己把该说的说完——
    待确认几条、今天炼哪只、心力多少、八道各在哪。
    """
    import render          # 顶层不 import：render 会拉起整个渲染链，按需再载
    con = connect()
    n_pend = con.execute("SELECT COUNT(*) c FROM evidence WHERE confirmed=0").fetchone()["c"]
    print("\n═══ 今天 ═══")
    if n_pend:
        print(f"  ⚠ 有 {n_pend} 条证据待确认 —— 面板上还没算进道痕")
    else:
        print("  ✓ 没有待确认的证据")
    g, why = render.pick_today(con)
    print(f"\n  今日一炼：{g['name']} · {g['practice']}")
    print(f"    {why}")
    for c in heart_reading(con):
        ap = c["self"]
        n = ap["capacity"] if ap else c["derived"]
        src = "自述" if ap else "按记录推（下限）"
        print(f"  {c['label']}心力：{n} 件 · {src}")
    print("\n  八道： " + " · ".join(
        f"{d['name']} {REALMS[d['realm_index']]}" for d in
        con.execute("SELECT * FROM daos WHERE active=1 ORDER BY realm_index DESC, name")))
    print("  面板： personskill/panel.html")


def note(text: str):
    """顺手记一条 —— 追加到 data/task.md 的当天段落。

    「越简单越好」：记录本来就该是随手的事。格式沿用你原来的，
    **不改你的写法**，只是替你把它放对位置（免得开文件找日期）。
    """
    d = _d.today()
    head = f"###### {d.strftime('%Y/%m/%d')}"
    body = TASKLOG.read_text(encoding="utf-8") if TASKLOG.exists() else ""
    if head in body:
        i = body.index(head) + len(head)
        body = body[:i] + f"\n\n{text}" + body[i:]
    else:
        body = f"{head}\n\n{text}\n\n{body}"
    TASKLOG.write_text(body, encoding="utf-8")
    print(f"✓ 已记进 data/task.md · {head[7:]}\n  {text}")


# 中文别名 —— 日常说中文，命令也该说中文。等价，不是另一套。
ALIASES = {
    "今日": "today", "跑": "rebuild", "看": "status", "检": "check",
    "面": "render", "炼": "feed", "升": "promote", "心力": "heart",
    "记": "note", "确认": "confirm", "测": "selftest", "建": "init",
}


def main():
    # 不带参数 = 跑今天（原来默认是 render，等于跑完数据不看结论）
    cmd = ALIASES.get(sys.argv[1], sys.argv[1]) if len(sys.argv) > 1 else "today"
    if cmd == "init":
        import seed, render
        seed.run()
        render.render()
    elif cmd in ("rebuild", "today"):
        ok = rebuild()
        if not ok:
            print("\n⚠ 重建完成，但自检未通过——上面标 ✗ 的项需要处理。")
            sys.exit(1)
        if cmd == "today":
            brief()
    elif cmd == "note":
        if len(sys.argv) < 3:
            print('用法：python run.py 记 "今天做了什么"')
            return
        note(" ".join(sys.argv[2:]))
    elif cmd == "heart":
        if len(sys.argv) < 3:
            print("用法：python run.py 心力 <件数> [日|周] [心境] [精力]")
            print("　例：python run.py 心力 12 周 无波 稳")
            print("　不记也行 —— 面板会按记录自己推一个下限出来。")
            return
        try:
            n = int(sys.argv[2])
        except ValueError:
            print(f"✗ 心力要一个数（件），收到 {sys.argv[2]!r}")
            sys.exit(1)
        hz = "week" if "周" in sys.argv[3:4] or not sys.argv[3:4] else "day"
        rest = [a for a in sys.argv[3:] if a not in ("日", "周")]
        record_heart(connect(), n, hz, rest[0] if rest else "", rest[1] if len(rest) > 1 else "")
        print(f"✓ 已记心力：{'本周' if hz == 'week' else '今日'} {n} 件")
        import render
        render.render()
    elif cmd == "render":
        import render
        render.render()
    elif cmd == "confirm":
        # 只有用户明确授权时才能跑（硬规矩：AI 不得自行确认自己抽的证据）
        from db import confirm_evidence
        con = connect()
        keep = [int(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else []
        ids = [r["id"] for r in con.execute("SELECT id FROM evidence WHERE confirmed=0")
               if r["id"] not in keep]
        n = confirm_evidence(con, ids)
        print(f"✓ 已确认 {n} 条" + (f"，保留 {len(keep)} 条待议：{keep}" if keep else ""))
        import render
        render.render()
    elif cmd == "promote":
        # 境界不可自评：这里只记录**用户亲口给的达成事件**，程序不判断"够不够格"。
        from db import promotion_candidates, promote
        con = connect()
        if len(sys.argv) < 4:
            print("各道的下一级门槛（境界由「达成事件」证明，不可自评）：\n")
            for c in promotion_candidates(con):
                if c["next"] is None:
                    tail = "已至道主"
                else:
                    tail = f"→ {REALMS[c['next']]}：{c['event']}"
                print(f"  {c['dao']:<6} 现「{REALMS[c['realm']]}」  {tail}")
            print('\n用法：python run.py promote <道名> "你达成了什么事"')
            return
        dao = sys.argv[2]
        event = " ".join(sys.argv[3:]).strip()
        try:
            to = promote(con, dao, event)
        except (KeyError, ValueError) as e:
            print(f"✗ {e}")
            sys.exit(1)
        print(f"✓ {dao} 晋升到「{REALMS[to]}」\n  事件：{event}")
        import render
        render.render()
    elif cmd == "feed":
        # 「炼了」—— 记下日期，那只蛊的饥饱立刻由数据推出来。
        from db import connect as _c, feed_gu
        con = _c()
        if len(sys.argv) < 3:
            print("用法：python run.py feed <蛊名>    （或加日期：python run.py feed 人言蛊 2026-10-14）")
            return
        row = con.execute("SELECT id, state FROM gu WHERE name=?", (sys.argv[2],)).fetchone()
        if row is None:
            print(f"✗ 没有这只蛊：{sys.argv[2]}")
            sys.exit(1)
        on = sys.argv[3] if len(sys.argv) > 3 else None
        s = feed_gu(con, row["id"], on)
        print(f"✓ {sys.argv[2]}：「{row['state']}」→「{s}」")
        import render
        render.render()
    elif cmd == "check":
        if not check():
            sys.exit(1)
    elif cmd == "status":
        status()
    elif cmd == "web":
        # 端口走 argv[2]（argv[1] 是 "web" 本身）。
        # 曾经 web.py 在导入时读 sys.argv[1]，于是这条命令一 import 就 ValueError。
        import web
        web.serve(int(sys.argv[2]) if len(sys.argv) > 2 else web.DEFAULT_PORT)
    elif cmd == "selftest":
        import render
        print("回归测试：改数据，面板是否跟着变\n" + "─" * 44)
        selftest()
        render.render()   # 恢复成真实数据的面板
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
