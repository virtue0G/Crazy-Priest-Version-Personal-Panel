"""把已验证的数据灌入库。

框架设定（八道 / 蛊 / 杀招 / 阶梯 / 空窍）写在本文件里——它们不含隐私。
**证据**不在这里，由 baseline.load() 从 JSON 装载：
`data/baseline.json` 是真实记录（不入库），`demo/baseline.json` 是脱敏示例（入库）。
weight 单位为道痕。
"""
from baseline import load, source_label
from db import connect

# ── 八道 ──────────────────────────────────────────────
DAOS = [
    # name,     domain,            layer, origin, realm, mission
    ("律道", "方法论沉淀", "常修", "原生", 0, None),
    ("智道", "因果辨别",   "常修", "原生", 0, None),
    ("炼道", "建模 · 调参", "主修", "原生", 0, None),
    ("阵道", "数据治理",   "常修", "原生", 0, None),
    ("星道", "商业洞察",   "常修", "原生", 0, None),
    ("信道", "表达 · 说服 · 写作", "常修", "原生", 0, None),
    ("智造道", "AI 应用 · 智能创造", "常修", "衍生", 0, "创造真正的智慧智能"),
    ("器道", "工具 · 造物", "常修", "原生", 0, None),
]
# 衍生道的母道
DAO_PARENTS = [("智造道", "智道"), ("智造道", "炼道"), ("智造道", "器道")]

# ── 蛊（与道是多对多「相关」）──────────────────────────
GU = [
    # name,     tier, kind, vital, state, 日常练法, 相关道
    ("因果蛊", 3, "凡", 1, "饱食", None, ["智道", "炼道", "星道"]),
    ("火候蛊", 1, "凡", 0, "饱食", "复现一个旧模型，只改一处参数看差异", ["炼道", "器道", "智造道"]),
    ("人言蛊", 1, "凡", 0, "濒死", "影子跟读 10 分钟", ["信道", "智造道", "律道"]),
    ("役智蛊", 1, "凡", 0, "微饥", "用 AI 做一件小东西（半小时内）", ["智造道", "器道"]),
    ("机关蛊", 1, "凡", 0, "饱食", "写一个小脚本解决一个重复动作", ["器道", "炼道"]),
    ("先见蛊", 1, "凡", 0, "饱食", None, ["星道", "智道"]),
    ("铺路蛊", 1, "凡", 0, "饱食", None, ["阵道", "器道", "炼道"]),
    ("准绳蛊", 1, "凡", 0, "微饥", None, ["律道", "阵道"]),
    ("量天蛊", 6, "仙", 0, "在炼", None, []),     # 仙蛊·在炼，四味合炼而成
]

# ── 证据 / 杀招 / 人物面板 ────────────────────────────
# 都不写在这里。真实记录在 data/baseline.json（不入库），
# 脱敏示例在 demo/baseline.json（入库）——由 baseline.load() 二选一。
#
# 连杀招的 note 和 profile 一起搬走，是因为：note 写的是「人的判断」，
# profile 是自评，aperture 是读数——都是个人内容，和证据一个性质。
# 改这些内容请改 JSON，不要改本文件。
# 杀招 ↔ 蛊（多对多）。材料里那些「尚未成形的蛊」不在表中，另行文字说明。
MOVE_GU = {
    "量化回测": ["火候蛊", "因果蛊", "铺路蛊"],
    "把研究交出去": ["人言蛊", "因果蛊", "役智蛊"],
    "知识地图": ["因果蛊", "铺路蛊", "人言蛊"],
    "AI 分析工具": ["役智蛊", "火候蛊", "因果蛊", "人言蛊"],
    "行业研究": ["先见蛊", "火候蛊"],
}

# ── 晋升事件：阶梯，不是一句口号 ─────────────────────
# 每一级 = 到该级所需的「达成事件」，索引 i 对应「升到 REALMS[i]」。
#
# 铁律（用户 2026-09-24 指出）：**门槛必须是"下一件你够得着的事"，不是终极理想。**
# 反面教材：智造道原本把「造出东西能自己思考」当成「大师」的门槛——
# 那是全世界没人敢说做到的事，等于这道永远不可能晋升。
# 现在它被放回阶梯顶端（道主），大师换成「你做的东西被人拿去用了一次」。
#
# 递进骨架：第一次做到 → 被复用 → 脱离你也能跑 → 跨领域仍成立 → 别人照你的做 → 开创
LADDERS = {
    "律道": [
        "你立的一条律条，改变了你之后的实际行为——同错不再犯",
        "这条律条在同一类项目里被复用第二次，且省下了返工",
        "别人遇到同类问题，开始来问你的那套查法",
        "你的查法被用在完全不同的领域，仍然管用",
        "有人按你的查法做事，即使你不在场、也没问过你",
        "你立的律条，成了别人默认的规矩",
    ],
    "智道": [
        "你识破一条一直起作用、却没人命名的规律，并为它命名",
        "你起的这个名字被用在下一次判断上，且判断对了",
        "别人拿你起的名字，去解释他们自己的问题",
        "信息不全时你就敢下判断，事后被验证",
        "你的判断成为别人做决定的依据",
        "你开辟了一条前人没有的辨别路径",
    ],
    "炼道": [
        "你独立合炼出一只新蛊（模型／流程），且它真能用",
        "这只蛊换一个项目直接复用，没大改",
        "别人用你炼的蛊，去做他们自己的事",
        "不用试你就知道哪只蛊合用，且猜对了",
        "你的炼法被写进流程，成了默认做法",
        "你开创了一种新的炼法",
    ],
    "阵道": [
        "你布的一个阵，在你不在场时依然运转",
        "这个阵接进新数据源，不用重搭",
        "别人把他们的东西接进你的阵",
        "你的阵跨了两种完全不同的数据形态，仍然稳",
        "你的阵成了大家的默认底座",
        "你开创了一种新的阵型",
    ],
    "星道": [
        "你写下一个判断，并写明它会被什么验证或推翻",
        "这个判断，被时间验证了",
        "你的判断改变了别人的实际动作",
        "在别人看不出规律的地方，你看出了走向，且被验证",
        "你的判断成了别人下注的依据",
        "你开创了一套看商业的框架",
    ],
    "信道": [
        "你说的话，被人复述或引用了一次",
        "有人因为你的话，改了他们的做法",
        "你把一件难懂的事，讲到外行也懂了",
        "你的表达改变了对方的立场",
        "别人用你的话，去说服第三方",
        "你开创了一种新的表达方式",
    ],
    "智造道": [
        "你做的东西，被别人拿去用了一次（哪怕很小）",
        "它被别人反复用，而你没在旁边教",
        "它处理了你没预设过的情况",
        "它产出了你没想到的东西",
        "它能自己改进自己",
        "它真能自己思考——创造真正的智慧智能",
    ],
    "器道": [
        "你造的一件器，被别人拿去用了一次",
        "别人反复用它，而你没在旁边教",
        "你的器被用在你想不到的地方",
        "别人在你器的基础上，造出了新器",
        "你的器成了这件事的默认工具",
        "你开创了一类器",
    ],
}


def run(reset: bool = True):
    data, src = load()
    EV, MV = data["evidence"], data["moves"]
    PF, AP = data["profile"], data["aperture"]
    con = connect()
    if reset:
        for t in ("dao_parents", "gu_dao", "evidence_dao", "realms_log", "daily",
                  "aperture", "killer_move_gu", "killer_moves", "gu", "evidence",
                  "daos", "profile", "proof_ladder", "wishes"):
            con.execute(f"DELETE FROM {t}")

    ids = {}
    for name, domain, layer, origin, realm, mission in DAOS:
        cur = con.execute(
            "INSERT INTO daos(name,domain,layer,origin,realm_index,mission) VALUES(?,?,?,?,?,?)",
            (name, domain, layer, origin, realm, mission))
        ids[name] = cur.lastrowid
    for child, parent in DAO_PARENTS:
        con.execute("INSERT INTO dao_parents VALUES(?,?)", (ids[child], ids[parent]))

    gu_ids = {}
    for name, tier, kind, vital, state, practice, daos in GU:
        cur = con.execute(
            "INSERT INTO gu(name,tier,kind,is_vital,state,practice) VALUES(?,?,?,?,?,?)",
            (name, tier, kind, vital, state, practice))
        gu_ids[name] = cur.lastrowid
        for d in daos:
            con.execute("INSERT INTO gu_dao VALUES(?,?)", (cur.lastrowid, ids[d]))

    for k, v in PF.items():
        con.execute("INSERT INTO profile VALUES(?,?)", (k, v))

    for ts, text, stype, alloc in EV:
        cur = con.execute(
            "INSERT INTO evidence(ts,text,source_type) VALUES(?,?,?)", (ts, text, stype))
        for dao, w in alloc:
            con.execute("INSERT INTO evidence_dao VALUES(?,?,?)", (cur.lastrowid, ids[dao], w))

    move_ids = {}
    for name, status, materials, note, seq in MV:
        cur = con.execute("INSERT INTO killer_moves(name,status,materials,note,seq) VALUES(?,?,?,?,?)",
                          (name, status, materials, note, seq))
        move_ids[name] = cur.lastrowid
    for move_name, gu_names in MOVE_GU.items():
        for gn in gu_names:
            con.execute("INSERT INTO killer_move_gu VALUES(?,?)", (move_ids[move_name], gu_ids[gn]))

    # 晋升阶梯：第 1 条是「升到大师」的门槛，故 to_realm_index 从 1 起（0 是普通，无需门槛）
    for dao_name, rungs in LADDERS.items():
        for to_realm, desc in enumerate(rungs, start=1):
            con.execute("INSERT INTO proof_ladder VALUES(?,?,?)", (ids[dao_name], to_realm, desc))

    # 读数两种口径并存 —— 按长度分派，**不迁移、不改写**：
    #   4 元组 = 旧口径 (date, 真元%, 心境, 精力)。真元被重新定义为「心力」后，
    #            这条读数不再是同一个量，**不能换算、也不该丢掉**：它是当初真写下的一句话。
    #            故 horizon 留空，面板不把它当心力读（硬规矩 2：不许拿推算冒充事实）。
    #   5 元组 = 新口径 (date, 日/周, 心力件数, 心境, 精力)。
    for row in AP:
        if len(row) == 5:
            con.execute("INSERT INTO aperture(date,horizon,capacity,mood_text,energy_note) "
                        "VALUES(?,?,?,?,?)", row)
        else:
            con.execute("INSERT INTO aperture(date,essence_pct,mood_text,energy_note) "
                        "VALUES(?,?,?,?)", row)
    # daily 不预置任何行：它是「炼了没有」的流水，预置就等于替用户谎报一次完成。
    # 今日炼什么由 render.pick_today 现算，与 daily 的分工是「计划 vs 事实」。
    con.commit()

    print(f"✓ 已灌入：{len(DAOS)} 道 / {len(GU)} 蛊 / {len(EV)} 条证据 / {len(MV)} 记杀招"
          f"　证据来源：{source_label(src)}")
    return con


if __name__ == "__main__":
    run()
