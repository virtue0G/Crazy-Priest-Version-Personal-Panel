"""基线数据装载：真实记录与脱敏示例的分界。

- `data/baseline.json`  —— 真实记录。`.gitignore` 挡住，**绝不入库**。
- `demo/baseline.json`  —— 脱敏示例。随仓库分发，让空仓库 clone 下来也能跑出面板。

**代码里不再出现任何真实记录**——这里是唯一的读取口。
以后要改基线数据，改 JSON，不要改 .py。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "data" / "baseline.json"
DEMO = ROOT / "demo" / "baseline.json"


def _rows(seq):
    """JSON 的 list → DB 层惯用的 tuple，含 [(道, 权重)…] 二元组。"""
    return [(r[0], r[1], r[2], [(d, w) for d, w in r[3]]) for r in seq]


def load():
    """→ (数据, 来源 Path)。

    来源落在 `data/` 就是真实记录，落在 `demo/` 就是脱敏示例——
    调用方把它打进输出，**面板上看得见自己跑的是哪一份**。
    """
    src = REAL if REAL.exists() else DEMO
    if not src.exists():
        raise FileNotFoundError(f"基线数据缺失：{REAL} 与 {DEMO} 都不存在")
    raw = json.loads(src.read_text(encoding="utf-8"))
    return {
        "evidence": _rows(raw["evidence"]),
        "new": _rows(raw["new"]),
        "wishes": [tuple(w) for w in raw["wishes"]],
        # 杀招的 note 是「人的判断」，profile / aperture 是自评与读数——
        # 这三样都是个人内容，和证据一样不入代码。
        "moves": [tuple(m) for m in raw["moves"]],
        "profile": dict(raw["profile"]),
        "aperture": [tuple(a) for a in raw["aperture"]],
    }, src


def source_label(src: Path) -> str:
    """给输出用的一行来源说明。"""
    return f"{src.parent.name}/{src.name}" + ("（真实记录）" if src == REAL else "（脱敏示例）")
