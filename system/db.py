"""数据库层 —— 按《产品文档》§5 的表设计。

A（Claude Code 技能式）与 B（独立应用）共用这一层，将来换壳不换芯。
"""
import sqlite3
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
CREATE TABLE IF NOT EXISTS aperture(
  id INTEGER PRIMARY KEY, date TEXT,
  essence_pct INTEGER, mood_text TEXT, energy_note TEXT, stone_note TEXT
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


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    # 迁移：老库补列
    cols = {r["name"] for r in con.execute("PRAGMA table_info(evidence)")}
    if "confirmed" not in cols:
        con.execute("ALTER TABLE evidence ADD COLUMN confirmed INTEGER DEFAULT 1")
    gcols = {r["name"] for r in con.execute("PRAGMA table_info(gu)")}
    if "practice" not in gcols:
        con.execute("ALTER TABLE gu ADD COLUMN practice TEXT")
    return con


def dao_marks(con, dao_id: int, confirmed: int | None = None) -> float:
    """道痕 = 该道证据权重之和。只增不减。

    confirmed=1 只算已确认（进面板）；confirmed=0 只算待确认。None 则全算。
    """
    q = ("SELECT COALESCE(SUM(ed.weight),0) AS m FROM evidence_dao ed "
         "JOIN evidence e ON e.id = ed.evidence_id WHERE ed.dao_id = ?")
    args = [dao_id]
    if confirmed is not None:
        q += " AND e.confirmed = ?"
        args.append(confirmed)
    return round(con.execute(q, args).fetchone()["m"], 1)


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


def add_evidence(con, ts, text, source_type, alloc, confirmed=0):
    """追加一条证据。alloc = [(道名, 权重), …]；权重按分配、总和守恒。"""
    cur = con.execute(
        "INSERT INTO evidence(ts, text, source_type, confirmed) VALUES(?,?,?,?)",
        (ts, text, source_type, confirmed))
    eid = cur.lastrowid
    for dao_name, w in alloc:
        row = con.execute("SELECT id FROM daos WHERE name=?", (dao_name,)).fetchone()
        if row is None:
            raise KeyError(f"未知的道：{dao_name}")
        con.execute("INSERT INTO evidence_dao VALUES(?,?,?)", (eid, row["id"], w))
    return eid


if __name__ == "__main__":
    connect()
    print(f"✓ 已初始化 {DB_PATH}")
