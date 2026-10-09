"""抽取：把新记录转成证据。

AI 提议（confirmed=0）→ 用户确认后才计道痕。
抽取规则见 SKILL.md：source_type 取 产出/协作/学习/踩坑/愿望。
记录本身由 baseline.load() 装载，不在本文件里。
"""
from baseline import load, source_label
from db import connect, add_evidence

# NEW / WISHES 不写在这里。真实记录在 data/baseline.json（不入库），
# 脱敏示例在 demo/baseline.json（入库）——由 baseline.load() 二选一。
# 改基线数据请改 JSON，不要改本文件。


def run():
    """只追加新证据（confirmed=0）。今日一炼由 render.py 从数据推出，此处不写死。"""
    data, src = load()
    NEW, WISHES = data["new"], data["wishes"]
    con = connect()
    for ts, text, stype, alloc in NEW:
        add_evidence(con, ts, text, stype, alloc, confirmed=0)
    con.execute("DELETE FROM wishes")
    for ts, text, note in WISHES:
        con.execute("INSERT INTO wishes(ts, text, note) VALUES(?,?,?)", (ts, text, note))
    con.commit()
    print(f"✓ 已提议 {len(NEW)} 条新证据（待确认）· 记下 {len(WISHES)} 条愿望（0 痕）"
          f"　来源：{source_label(src)}")
    return con


if __name__ == "__main__":
    run()
