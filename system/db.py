"""数据库层 —— 按《产品文档》§5 的表设计。

A（Claude Code 技能式）与 B（独立应用）共用这一层，将来换壳不换芯。
"""
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "growth.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daos(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  domain TEXT,
  layer TEXT DEFAULT '常修',           -- 主修 / 常修 / 游历
  origin TEXT DEFAULT '原生',           -- 原生 / 衍生 / 开创
  realm_index INTEGER DEFAULT 0,        -- 0普通 1大师 2宗师 3大宗师 4准无上 5无上 6道主
  mission TEXT,
  active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dao_parents(
  dao_id INTEGER, parent_dao_id INTEGER, PRIMARY KEY(dao_id, parent_dao_id)
);
CREATE TABLE IF NOT EXISTS gu(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  tier INTEGER DEFAULT 1,
  kind TEXT DEFAULT '凡',               -- 凡 / 仙
  is_vital INTEGER DEFAULT 0,           -- 本命蛊
  fed_at TEXT,
  state TEXT DEFAULT '饱食',            -- 饱食/微饥/饥饿/濒死/饿死·沉睡
  practice TEXT,                        -- 日常练法（今日一炼的候选）
  note TEXT
);
CREATE TABLE IF NOT EXISTS profile(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS gu_dao(      -- 蛊与道是多对多「相关」，非隶属
  gu_id INTEGER, dao_id INTEGER, PRIMARY KEY(gu_id, dao_id)
);
CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY,
  ts TEXT,
  text TEXT,
  source_type TEXT,                     -- 产出/协作/学习/踩坑/愿望
  confirmed INTEGER DEFAULT 1,          -- AI 抽取的一律先置 0，用户确认后才计道痕
  ext_key TEXT,                         -- 外部回执的稳定标识；手写证据为 NULL
  origin TEXT,                          -- 出处：指回原文。指不回去的不收
  alloc_edited INTEGER DEFAULT 0,       -- 分配被「人」改过。没改过的，回执改了提议就该跟着走
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS evidence_dao( -- 一条证据可归属多道，权重守恒
  evidence_id INTEGER, dao_id INTEGER, weight REAL,
  PRIMARY KEY(evidence_id, dao_id)
);
CREATE TABLE IF NOT EXISTS killer_moves(
  id INTEGER PRIMARY KEY,
  name TEXT, status TEXT, materials TEXT, note TEXT, seq INTEGER DEFAULT 99
);
CREATE TABLE IF NOT EXISTS killer_move_gu( -- 杀招由哪几味蛊合炼（多对多）
  move_id INTEGER, gu_id INTEGER, PRIMARY KEY(move_id, gu_id)
);
CREATE TABLE IF NOT EXISTS aperture(   -- 空窍读数：心力（真元）
  id INTEGER PRIMARY KEY, date TEXT,
  essence_pct INTEGER,                 -- 旧口径「真元 %」，已废；只为保住历史行不被改写
  mood_text TEXT, energy_note TEXT, stone_note TEXT,
  horizon TEXT,                        -- day / week：这条读数管一天还是管一周
  capacity INTEGER                     -- 心力：该周期内能做完／已做完的事，单位「件」
);
CREATE TABLE IF NOT EXISTS realms_log(   -- 晋升只由「事件」写入，不靠自评
  id INTEGER PRIMARY KEY, dao_id INTEGER,
  from_realm INTEGER, to_realm INTEGER,
  event_desc TEXT, achieved_at TEXT
);
CREATE TABLE IF NOT EXISTS proof_ladder( -- 每一级的「达成事件」：阶梯，不是一句口号
  dao_id INTEGER, to_realm_index INTEGER, event_desc TEXT,
  PRIMARY KEY(dao_id, to_realm_index)
);
CREATE TABLE IF NOT EXISTS daily(
  id INTEGER PRIMARY KEY, date TEXT, action TEXT,
  minutes INTEGER, done INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS wishes(       -- 愿望：想做但没做。0 道痕，但**记下缺口**
  id INTEGER PRIMARY KEY, ts TEXT, text TEXT,
  origin_evidence_id INTEGER,            -- 由哪条证据降级而来（可溯源）
  note TEXT
);
"""

REALMS = ["普通", "大师", "宗师", "大宗师", "准无上大宗师", "无上大宗师", "道主"]

# 蛊的饥饱档位（天数，闭区间下界）。来自 SKILL.md「阈值速查」。
# 上界不含：14 天以内算饱食，超过 14 天就掉到微饥，依此类推。
GU_LADDER = [(14, "饱食"), (30, "微饥"), (90, "饥饿"), (180, "濒死")]
GU_STARVED = "饿死·沉睡"

# ── 心力（真元）──────────────────────────────────────────
#
# 用户 2026-10-16 定的口径：**真元 = 心力 = 一段时间内能做完的事的量**，单位「件」，
# 分「日」「周」两个周期。它**能量化**，而且**能从记录里算出来** —— 所以默认就该算，
# 不该让人手填（用户原话：「操作越简单越好，尽量不要让用户有多余的动作」）。
#
# 推法：该周期内 source_type ∈ (产出, 踩坑) 的证据条数。
# 这两类才是「做完的事」；协作是参与、学习是输入，都不算做完。
#
# ⚠ **推出来的是下限**：不记就不算。所以面板上必须标明是推的，
# 绝不能让一个算出来的数冒充自述（硬规矩 4：能算的现算；硬规矩 2：不许拿推算当事实）。
HEART_SOURCES = ("产出", "踩坑")


def horizon_range(horizon: str, on: str | None = None) -> tuple[str, str]:
    """一条读数管哪段日子。week = 所在周的周一~周日（ISO 周）。"""
    d = date.fromisoformat(on) if isinstance(on, str) else (on or date.today())
    if horizon == "week":
        mon = d - timedelta(days=d.weekday())
        return mon.isoformat(), (mon + timedelta(days=6)).isoformat()
    return d.isoformat(), d.isoformat()


def derive_heart(con, horizon: str, on: str | None = None) -> int:
    """推出来的心力读数（件）。**只在没有自述时用它，且永远标明是推的。**"""
    lo, hi = horizon_range(horizon, on)
    return con.execute(
        f"SELECT COUNT(*) c FROM evidence WHERE confirmed=1 AND ts BETWEEN ? AND ? "
        f"AND source_type IN ({','.join('?' * len(HEART_SOURCES))})",
        (lo, hi, *HEART_SOURCES)).fetchone()["c"]


def heart_reading(con, on: str | None = None) -> list[dict]:
    """面板要的读数：每个周期一条，**自述优先、推演兜底**，并说清是哪一种。

    自述是「人的决定」，权威；推演只是下限。两者都给出来，
    但不混成一个数 —— 面板上要能一眼看出这条数是人说的还是算的。
    """
    on = on or date.today().isoformat()
    out = []
    for h, label in (("week", "本周"), ("day", "今日")):
        lo, hi = horizon_range(h, on)
        row = con.execute(
            "SELECT * FROM aperture WHERE horizon=? AND date<=? ORDER BY date DESC LIMIT 1",
            (h, on)).fetchone()
        out.append({
            "horizon": h, "label": label, "lo": lo, "hi": hi,
            "self": row,                                  # 自述（可能为 None）
            "derived": derive_heart(con, h, on),          # 推演（下限）
        })
    return out


def record_heart(con, capacity: int, horizon: str = "week", mood: str = "",
                 energy: str = "", on: str | None = None) -> None:
    """人的自述读数 —— 覆盖推演。写进 aperture，和证据一样属于「人的决定」。"""
    if horizon not in ("day", "week"):
        raise ValueError(f"horizon 只能是 day/week，收到 {horizon!r}")
    con.execute("INSERT INTO aperture(date,horizon,capacity,mood_text,energy_note) "
                "VALUES(?,?,?,?,?)",
                (on or date.today().isoformat(), horizon, int(capacity), mood, energy))
    con.commit()


def derive_gu_state(fed_at: str | None, today=None) -> str | None:
    """按「上次炼是哪天」推饥饱。

    `fed_at` 为空 → 返回 None，表示**推不出来，保留原值**。
    这不是偷懒：老库里的 state 是当初写下的字面值，凭空给它编一个喂养日期，
    等于伪造一条事实（硬规矩 2）。等它真的被喂过一次，推导才接管。
    """
    if not fed_at:
        return None
    from datetime import date as _d
    t = today or _d.today()
    if isinstance(t, str):
        t = _d.fromisoformat(t)
    f = _d.fromisoformat(fed_at) if isinstance(fed_at, str) else fed_at
    days = (t - f).days
    for limit, state in GU_LADDER:
        if days <= limit:
            return state
    return GU_STARVED


def refresh_gu_states(con, today=None) -> int:
    """把 fed_at 推出来的状态回写进 gu.state。

    **回写而不是现算**，是为了让现成的 SQL 继续能用 ——
    `render.pick_today` 是按 `ORDER BY CASE state WHEN '濒死' THEN 0 …` 排的，
    状态若只活在 Python 里，那条排序就得跟着重写。回写一次，四处都不用动。
    """
    n = 0
    for r in con.execute("SELECT id, fed_at, state FROM gu"):
        s = derive_gu_state(r["fed_at"], today)
        if s and s != r["state"]:
            con.execute("UPDATE gu SET state=? WHERE id=?", (s, r["id"]))
            n += 1
    if n:
        con.commit()
    return n


def snapshot_gu_fed(con) -> dict:
    """{蛊名: 上次炼的日期}。

    重建会按 seed 里的字面值把 gu 表整个重灌，喂过的记录不先存下来就没了 ——
    「炼了一次」是用户做的事，和确认一样属于「人的决定」（硬规矩 6）。
    """
    return {r["name"]: r["fed_at"] for r in con.execute(
        "SELECT name, fed_at FROM gu WHERE fed_at IS NOT NULL")}


def apply_gu_fed(con, prior: dict) -> int:
    n = 0
    for name, d in prior.items():
        n += con.execute("UPDATE gu SET fed_at=? WHERE name=?", (d, name)).rowcount
    con.commit()
    return n


def snapshot_realms(con) -> list[tuple]:
    """[(道名, from_realm, to_realm, 事件, 日期)] —— 晋升流水。

    重建会按 seed 把 realms_log 整个清空重灌，而**晋升是这系统里最纯的
    「人的决定」**：硬规矩 1 说境界不可自评，只有用户亲口给的达成事件才算数。
    不先存下来，用户白晋升一次 —— 和 evidence 的确认、gu.fed_at 是同一类病
    （硬规矩 6）。这一条真的漏了：`run.py promote` 之后一 rebuild，境界就回滚。

    按**道名**存，不按 id：重建后 dao_id 会重排。
    """
    return [(r["name"], r["from_realm"], r["to_realm"], r["event_desc"], r["achieved_at"])
            for r in con.execute(
                "SELECT d.name, r.from_realm, r.to_realm, r.event_desc, r.achieved_at "
                "FROM realms_log r JOIN daos d ON d.id=r.dao_id ORDER BY r.id")]


def apply_realms(con, prior: list[tuple]) -> int:
    """把晋升流水贴回去，并让 realm_index 跟着它走。

    realm_index **不另存一份真相** —— 它由 realms_log 推出（最后一笔到哪级就是哪级），
    这样「记录」与「当前境界」不可能各自漂移。check() 里有对应的一条不变式。
    """
    n = 0
    for name, fr, to, ev, at in prior:
        row = con.execute("SELECT id FROM daos WHERE name=?", (name,)).fetchone()
        if row is None:            # 道没了，这条晋升无处安放
            continue
        con.execute("INSERT INTO realms_log(dao_id,from_realm,to_realm,event_desc,achieved_at) "
                    "VALUES(?,?,?,?,?)", (row["id"], fr, to, ev, at))
        con.execute("UPDATE daos SET realm_index=? WHERE id=?", (to, row["id"]))
        n += 1
    con.commit()
    return n


def feed_gu(con, gu_id: int, on=None) -> str:
    """炼了一次 —— 记下日期并立刻刷新这只蛊的饥饱。"""
    from datetime import date as _d
    d = (on or _d.today())
    d = d.isoformat() if not isinstance(d, str) else d
    con.execute("UPDATE gu SET fed_at=? WHERE id=?", (d, gu_id))
    state = con.execute("SELECT fed_at FROM gu WHERE id=?", (gu_id,)).fetchone()
    s = derive_gu_state(state["fed_at"])
    con.execute("UPDATE gu SET state=? WHERE id=?", (s, gu_id))
    con.commit()
    return s


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    # 迁移：老库补列
    cols = {r["name"] for r in con.execute("PRAGMA table_info(evidence)")}
    if "confirmed" not in cols:
        con.execute("ALTER TABLE evidence ADD COLUMN confirmed INTEGER DEFAULT 1")
    if "ext_key" not in cols:
        con.execute("ALTER TABLE evidence ADD COLUMN ext_key TEXT")
    if "origin" not in cols:
        con.execute("ALTER TABLE evidence ADD COLUMN origin TEXT")
    if "alloc_edited" not in cols:
        con.execute("ALTER TABLE evidence ADD COLUMN alloc_edited INTEGER DEFAULT 0")
    gcols = {r["name"] for r in con.execute("PRAGMA table_info(gu)")}
    if "practice" not in gcols:
        con.execute("ALTER TABLE gu ADD COLUMN practice TEXT")
    acols = {r["name"] for r in con.execute("PRAGMA table_info(aperture)")}
    if "horizon" not in acols:
        con.execute("ALTER TABLE aperture ADD COLUMN horizon TEXT")
    if "capacity" not in acols:
        con.execute("ALTER TABLE aperture ADD COLUMN capacity INTEGER")
    # 部分唯一索引：手写证据 ext_key 为 NULL（SQLite 允许多个 NULL），
    # 外部回执每条只许一行 —— 这是幂等的兜底。
    # **必须放在 ALTER 之后**：老库若还没这列，建索引会直接失败。
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_evidence_ext_key "
                "ON evidence(ext_key) WHERE ext_key IS NOT NULL")
    return con


def dao_marks(con, dao_id: int, confirmed: int | None = None,
              digits: int | None = 1) -> float:
    """道痕 = 该道证据权重之和。只增不减。

    confirmed=1 只算已确认（进面板）；confirmed=0 只算待确认。None 则全算。

    `digits` 是**显示**用的舍入。做守恒校验时必须传 None ——
    否则就是拿「每道先舍入再相加」去比「逐条原始值相加」，
    两边天然差的正是舍入误差（8 道最多差 0.4）。以前权重都是 0.5 的整数倍，
    舍入无损，所以这个坑一直没露；一旦有 0.667 这种权重就会误报。
    """
    q = ("SELECT COALESCE(SUM(ed.weight),0) AS m FROM evidence_dao ed "
         "JOIN evidence e ON e.id = ed.evidence_id WHERE ed.dao_id = ?")
    args = [dao_id]
    if confirmed is not None:
        q += " AND e.confirmed = ?"
        args.append(confirmed)
    v = float(con.execute(q, args).fetchone()["m"])
    return round(v, digits) if digits is not None else v


def next_proof(con, dao_id: int, realm_index: int) -> str:
    """这道「下一级」的达成事件。已至道主则返回 '—'。"""
    row = con.execute("SELECT event_desc FROM proof_ladder WHERE dao_id=? AND to_realm_index=?",
                      (dao_id, realm_index + 1)).fetchone()
    return row["event_desc"] if row else "—"


def snapshot_confirmations(con) -> set:
    """记下「哪些证据已被确认」，用 (ts, text) 作键 —— 不依赖 id，因为重建会换 id。

    为什么需要：seed.run(reset=True) 会清空 evidence 表重建。确认是**用户做的决定**，
    不是种子数据；重建一次就抹掉，等于让用户白确认。曾真的发生过。
    """
    return {(r["ts"], r["text"]) for r in con.execute("SELECT ts, text FROM evidence WHERE confirmed=1")}


def apply_confirmations(con, prior: set) -> int:
    """把快照里的确认状态贴回去（按 ts+text 匹配）。"""
    n = 0
    for ts, text in prior:
        cur = con.execute("UPDATE evidence SET confirmed=1 WHERE confirmed=0 AND ts IS ? AND text=?",
                          (ts, text))
        n += cur.rowcount
    con.commit()
    return n


def confirm_evidence(con, ids=None) -> int:
    """把 AI 提议的证据转为已确认。ids=None 表示全部。

    确认是「人」的动作——AI 不得自行确认自己抽的东西（硬规矩 R1/R4）。
    """
    if ids is None:
        cur = con.execute("UPDATE evidence SET confirmed=1 WHERE confirmed=0")
    else:
        q = ",".join("?" * len(ids))
        cur = con.execute(f"UPDATE evidence SET confirmed=1 WHERE confirmed=0 AND id IN ({q})", list(ids))
    con.commit()
    return cur.rowcount


def next_realm(con, dao_id: int):
    """→ (下一级的 to_realm_index, 该级的达成事件)；已至道主则 None。"""
    cur = con.execute("SELECT realm_index FROM daos WHERE id=?", (dao_id,)).fetchone()
    if cur is None:
        return None
    nxt = cur["realm_index"] + 1
    row = con.execute("SELECT event_desc FROM proof_ladder WHERE dao_id=? AND to_realm_index=?",
                      (dao_id, nxt)).fetchone()
    return (nxt, row["event_desc"]) if row else None


def promotion_candidates(con) -> list[dict]:
    """各道的「下一级 + 门槛原文」——给 `run.py promote` 摆出来看。"""
    out = []
    for d in con.execute("SELECT id,name,realm_index FROM daos WHERE active=1 ORDER BY name"):
        n = next_realm(con, d["id"])
        out.append({"dao": d["name"], "realm": d["realm_index"],
                    "next": n[0] if n else None,
                    "event": n[1] if n else None})
    return out


def promote(con, dao_name: str, event_desc: str, on=None) -> int:
    """晋升一级。

    **必须由「达成事件」触发**（硬规矩 1）。这个函数只负责把**用户亲口给的
    那件事**记下来 —— 它不会自己判断「你够格了」。境界不可自评，判断权在人。
    """
    from datetime import date as _d
    row = con.execute("SELECT id, realm_index FROM daos WHERE name=?", (dao_name,)).fetchone()
    if row is None:
        raise KeyError(f"没有这条道：{dao_name}")
    n = next_realm(con, row["id"])
    if n is None:
        raise ValueError(f"{dao_name} 已至道主，上面没有更高的级了")
    if not event_desc.strip():
        raise ValueError("晋升必须写明「达成了什么事」—— 门槛不是自评，是事件")
    to_realm, needed = n
    con.execute("INSERT INTO realms_log(dao_id, from_realm, to_realm, event_desc, achieved_at) "
                "VALUES(?,?,?,?,?)",
                (row["id"], row["realm_index"], to_realm, event_desc.strip(),
                 (on or _d.today()).isoformat() if not isinstance(on, str) else on))
    con.execute("UPDATE daos SET realm_index=? WHERE id=?", (to_realm, row["id"]))
    con.commit()
    return to_realm


def add_evidence(con, ts, text, source_type, alloc, confirmed=0,
                 ext_key=None, origin=None):
    """追加一条证据。alloc = [(道名, 权重), …]；权重按分配、总和守恒。

    `ext_key` 给定 = 外部回执条目：先按它找，命中就更新正文并重写分配，
    **但绝不碰 confirmed** —— 确认是人的决定，脚本不许重置。

    道名先全部解析、再动表：这样有个别道名不存在时会**整条失败**，
    而不是留下一条「无归属的证据」把 check() 弄红。
    """
    ids = []
    for dao_name, w in alloc:
        row = con.execute("SELECT id FROM daos WHERE name=?", (dao_name,)).fetchone()
        if row is None:
            raise KeyError(f"未知的道：{dao_name}")
        ids.append((row["id"], w))

    if ext_key:
        row = con.execute("SELECT id, alloc_edited FROM evidence WHERE ext_key=?",
                          (ext_key,)).fetchone()
        if row:
            eid = row["id"]
            con.execute("UPDATE evidence SET ts=?, text=?, source_type=?, origin=? WHERE id=?",
                        (ts, text, source_type, origin, eid))
            # 分配被「人」改过就别覆盖 —— 回执的提议只在没人管的时候说了算。
            if not row["alloc_edited"]:
                con.execute("DELETE FROM evidence_dao WHERE evidence_id=?", (eid,))
                for did, w in ids:
                    con.execute("INSERT INTO evidence_dao VALUES(?,?,?)", (eid, did, w))
            return eid

    cur = con.execute(
        "INSERT INTO evidence(ts, text, source_type, confirmed, ext_key, origin) "
        "VALUES(?,?,?,?,?,?)", (ts, text, source_type, confirmed, ext_key, origin))
    eid = cur.lastrowid
    for did, w in ids:
        con.execute("INSERT INTO evidence_dao VALUES(?,?,?)", (eid, did, w))
    return eid


def alloc_of(con, evidence_id: int) -> str:
    """「道名 权重 · 道名 权重」—— 面板显示与网页回填共用同一种格式。"""
    rows = con.execute(
        "SELECT d.name, ed.weight FROM evidence_dao ed JOIN daos d ON d.id=ed.dao_id "
        "WHERE ed.evidence_id=? ORDER BY ed.weight DESC, d.name", (evidence_id,)).fetchall()
    return " · ".join(f'{r["name"]} {r["weight"]:g}' for r in rows)


def set_evidence_alloc(con, evidence_id: int, alloc, edited: bool = True) -> int:
    """整条替换某证据的道痕分配。

    空分配直接拒绝 —— 那会造出一条「无归属的证据」，`check()` 会红。
    只改 evidence_dao，**绝不动 confirmed**（确认仍是人的动作）。

    `edited=True`（网页调权）会打上「人改过」的标记，此后回执再改提议也不覆盖它。
    `edited=False`（把旧分配贴回）不打标记 —— 那只是恢复，不是新的决定。
    """
    if not alloc:
        raise ValueError("分配不能为空 —— 会造出无归属的证据")
    ids = []
    for dao_name, w in alloc:
        row = con.execute("SELECT id FROM daos WHERE name=?", (dao_name,)).fetchone()
        if row is None:
            raise KeyError(f"未知的道：{dao_name}")
        if float(w) < 0:
            raise ValueError(f"权重不能为负：{dao_name} {w}")
        ids.append((row["id"], float(w)))
    con.execute("DELETE FROM evidence_dao WHERE evidence_id=?", (evidence_id,))
    for did, w in ids:
        con.execute("INSERT INTO evidence_dao VALUES(?,?,?)", (evidence_id, did, w))
    if edited:
        con.execute("UPDATE evidence SET alloc_edited=1 WHERE id=?", (evidence_id,))
    con.commit()
    return len(ids)


def snapshot_confirmed_keys(con) -> set:
    """已被确认的**外部**条目的稳定键。

    为什么要它：`(ts, text)` 那套快照扛不住**正文漂移** ——
    回测一重跑，指标数字变了，text 就变了，那条确认就失配、掉回「待你确认」，
    变成天天重签。ext_key 不随正文漂移，所以由它兜住。
    """
    return {r["ext_key"] for r in con.execute(
        "SELECT ext_key FROM evidence WHERE confirmed=1 AND ext_key IS NOT NULL")}


def apply_confirmed_keys(con, keys) -> int:
    """把 ext_key 上的确认贴回（贴的是用户自己上一轮的决定，不是 AI 自确认）。"""
    n = 0
    for k in keys:
        n += con.execute("UPDATE evidence SET confirmed=1 WHERE confirmed=0 AND ext_key=?",
                         (k,)).rowcount
    con.commit()
    return n


def snapshot_external_alloc(con) -> dict:
    """{ext_key: [(道名, 权重), …]} —— 只取**被「人」改过**的外部条目。

    两个「不取」都是刻意的：
      · 手写记录不取 —— 它的分配以 `baseline.json` 为单一真相源，
        两处都能改必然打架。
      · 没被改过的外部条目不取 —— 那还是脚本的原提议。要是也快照，
        以后回执改了提议，面板却纹丝不动，看起来就像个 bug。
    """
    out: dict[str, list] = {}
    for r in con.execute(
        "SELECT e.ext_key k, d.name n, ed.weight w FROM evidence e "
        "JOIN evidence_dao ed ON ed.evidence_id=e.id JOIN daos d ON d.id=ed.dao_id "
        "WHERE e.ext_key IS NOT NULL AND e.alloc_edited=1"):
        out.setdefault(r["k"], []).append((r["n"], r["w"]))
    return out


def apply_external_alloc(con, prior: dict) -> int:
    """把用户改过的分配贴回去。重建不得抹掉「人的决定」。"""
    n = 0
    for k, alloc in prior.items():
        row = con.execute("SELECT id FROM evidence WHERE ext_key=?", (k,)).fetchone()
        if row is None:
            continue                      # 这条已被外部源撤下 —— 不复活它
        # edited=False：这是**贴回**、不是新的决定。传 True 会把每次重建都记成
        # 「人改过」，于是回执以后再也改不动这条分配 —— 正好和这个标记的用途相反。
        n += set_evidence_alloc(con, row["id"], alloc, edited=False)
    return n


if __name__ == "__main__":
    connect()
    print(f"✓ 已初始化 {DB_PATH}")
