"""入口 —— 一条命令跑完整条流水线。

用法：
    python run.py init      # 建库 + 灌已验证数据 + 出面板（第一次跑）
    python run.py render    # 只重新渲染面板（数据变了之后）
    python run.py rebuild   # 重置 → 灌数据 → 追加新证据 → 出面板
    python run.py check     # 完整性自检：跑一遍并核对信息无断链
    python run.py status    # 查看当前道痕与蛊的状态
    python run.py selftest  # 回归测试：改数据，面板必须跟着变
                            # （rebuild 结尾会自动跑一遍 check，跑通才算跑通）
    python run.py confirm   # 确认全部待确认证据（须用户授权）
    python run.py confirm 14 15   # 确认除 14、15 之外的全部
    python run.py web       # 起本地网页面板
"""
import sys
from pathlib import Path
from db import connect, REALMS, dao_marks

PANEL = Path(__file__).parent.parent / "panel.html"

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
    ]
    print("═══ 完整性 ═══")
    for name, n in tests:
        print(f"  {'✓' if n == 0 else '✗'} {name:<22}{n}")
        if n:
            bad.append(name)

    tot = con.execute("SELECT SUM(weight) s FROM evidence_dao ed JOIN evidence e "
                      "ON e.id=ed.evidence_id WHERE e.confirmed=1").fetchone()["s"] or 0
    per = sum(dao_marks(con, d["id"], confirmed=1) for d in con.execute("SELECT id FROM daos WHERE active=1"))
    ok = abs(tot - per) < 0.05
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


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "render"
    if cmd == "init":
        import seed, render
        seed.run()
        render.render()
    elif cmd == "rebuild":
        # 重置 → 灌已验证数据 → 追加新证据（待确认）→ 出面板
        #
        # ★ 关键：重建会清空 evidence 表，但**确认是用户做的决定，不是种子数据**。
        #   重建一次就抹掉，等于让人白确认——这件事真的发生过（17 条被抹）。
        #   故先按 (ts, text) 快照，重建后再贴回去。
        import seed, ingest, render
        from db import snapshot_confirmations, apply_confirmations
        con = connect()
        prior = snapshot_confirmations(con)
        seed.run()
        ingest.run()
        apply_confirmations(con, prior)
        render.render()
        if prior:
            # 真正要盯的不是「贴回几条」，而是「有没有哪条确认找不到它的证据了」——
            # 那才是被重建弄丢的用户决定。
            live = {(r["ts"], r["text"]) for r in con.execute("SELECT ts, text FROM evidence")}
            lost = prior - live
            print(f"✓ 已确认的 {len(prior)} 条中，{len(live & prior)} 条随重建保住"
                  + (f"，⚠ {len(lost)} 条因原文已不存在而失效" if lost else "（重建不抹人的决定）"))
        # 跑通才算跑通：重建完自动核对一遍。道痕守恒、标签配对这类问题人眼看不出，
        # 但一旦坏了，页面会照常显示——所以不能靠"看着没问题"。
        print()
        if not check():
            print("\n⚠ 重建完成，但自检未通过——上面标 ✗ 的项需要处理。")
            sys.exit(1)
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
    elif cmd == "check":
        if not check():
            sys.exit(1)
    elif cmd == "status":
        status()
    elif cmd == "web":
        import web
        web.serve()
    elif cmd == "selftest":
        import render
        print("回归测试：改数据，面板是否跟着变\n" + "─" * 44)
        selftest()
        render.render()   # 恢复成真实数据的面板
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
