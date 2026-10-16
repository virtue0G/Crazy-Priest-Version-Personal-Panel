"""抽取：把新记录转成证据。

AI 提议（confirmed=0）→ 用户确认后才计道痕。
抽取规则见 SKILL.md：source_type 取 产出/协作/学习/踩坑/愿望。
记录本身由 baseline.load() 装载，不在本文件里。
"""
import receipt
from baseline import load, source_label
from db import add_evidence, connect

# NEW / WISHES 不写在这里。真实记录在 data/baseline.json（不入库），
# 脱敏示例在 demo/baseline.json（入库）——由 baseline.load() 二选一。
# 改基线数据请改 JSON，不要改本文件。
#
# 外部产出（别的仓库跑出来的事实）走 receipt.py：登记表在 data/sources.json，
# 同样是「代码里没有内容，内容在数据里」。


def alloc_from_gu(con, gu_names, weight):
    """蛊 → 道 → 权重分配。

    先按蛊均分，蛊内部再按它挂的道均分。所以**一只道出现在越多只命名的蛊上，
    分到的越多** —— 它在这次产出里越核心。总和恰为 weight（权重守恒）。

    推不出来就抛 KeyError，由调用方整条跳过 —— 宁可这条不收，
    也不留一条无归属的证据把 check() 弄红。
    """
    per_gu = float(weight) / len(gu_names)
    acc: dict[str, float] = {}
    for gn in gu_names:
        row = con.execute("SELECT id FROM gu WHERE name=?", (gn,)).fetchone()
        if row is None:
            raise KeyError(f"未知的蛊「{gn}」")
        ds = con.execute(
            "SELECT d.name n FROM gu_dao gd JOIN daos d ON d.id=gd.dao_id WHERE gd.gu_id=?",
            (row["id"],)).fetchall()
        if not ds:
            raise KeyError(f"蛊「{gn}」没挂任何道")
        for r in ds:
            acc[r["n"]] = acc.get(r["n"], 0.0) + per_gu / len(ds)
    return sorted(((k, round(v, 3)) for k, v in acc.items()), key=lambda x: -x[1])


def run():
    """只追加新证据（confirmed=0）。今日一炼由 render.py 从数据推出，此处不写死。"""
    data, src = load()
    NEW, WISHES = data["new"], data["wishes"]
    con = connect()
    for ts, text, stype, alloc in NEW:
        add_evidence(con, ts, text, stype, alloc, confirmed=0)

    # ── 外部回执 ──────────────────────────────────────
    # 一律 confirmed=0：AI（脚本）不得自行确认自己产的东西（硬规矩 R1/R4）。
    items, warns = receipt.load_receipts()
    n_ext = 0
    for it in items:
        try:
            alloc = alloc_from_gu(con, it["gu"], it["weight"])
        except (KeyError, ZeroDivisionError) as e:
            warns.append(f"[{it['_source']}] {it['key']} 推不出道痕（{e}），跳过")
            continue
        add_evidence(con, it["ts"], it["text"], it.get("source_type", "产出"), alloc,
                     confirmed=0, ext_key=it["key"],
                     origin=f"{it['_project']}/{it['provenance']}")
        n_ext += 1

    con.execute("DELETE FROM wishes")
    for ts, text, note in WISHES:
        con.execute("INSERT INTO wishes(ts, text, note) VALUES(?,?,?)", (ts, text, note))
    con.commit()

    print(f"✓ 已提议 {len(NEW)} 条新证据（待确认）· 记下 {len(WISHES)} 条愿望（0 痕）"
          f"　来源：{source_label(src)}")
    if items or warns:
        print(f"✓ 外部回执：收下 {n_ext} 条，来自 {len({i['_source'] for i in items})} 个源"
              f"（待确认）")
    for w in warns:
        print(f"  ⚠ {w}")
    return con


if __name__ == "__main__":
    run()
