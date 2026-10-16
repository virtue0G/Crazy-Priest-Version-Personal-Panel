"""外部回执装载 —— 别的仓库跑出来的事实，怎么进这个系统。

- `data/sources.json` —— 登记表。被 `.gitignore` 挡住，**本机路径只允许出现在这里**。
- `demo/sources.json` —— 脱敏示例。随仓库分发，让空 clone 也能跑通外部流。

**这个仓库是公开的，所以代码里不出现任何绝对路径。** 路径只活在登记表里。

装载器只读文件、只校验**形状**（有没有 key / 出处 / 三分类）。
道名、蛊名是否真的存在，由 DB 层判定 —— 唯一真相在库里，不在这里。

修不了的地方一律**记 warning 跳过，不让 rebuild 崩**。跟 baseline 的「缺了就回落」一个精神。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "data" / "sources.json"
DEMO = ROOT / "demo" / "sources.json"

KINDS = ("strategy", "prediction")
STATUSES = ("open", "confirmed", "refuted")


def _resolve(p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else (ROOT / q)


def load_registry() -> tuple[list[dict], Path | None]:
    """→ (登记的外部源列表, 登记表 Path)。

    两份都没有不是错误 —— 那就是「没配外部源」，返回空。
    """
    src = REAL if REAL.exists() else DEMO
    if not src.exists():
        return [], None
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], src
    return [s for s in doc.get("sources", []) if s.get("enabled", True)], src


def _shape_ok(it: dict) -> str | None:
    """形状检查。返回 None 表示合格，否则返回「为什么不行」。"""
    for f in ("key", "text", "provenance"):
        if not str(it.get(f, "")).strip():
            return f"缺 {f}"
    if it.get("kind") not in KINDS:
        return f"kind 非法（只能是 {KINDS}）"
    if not it.get("gu"):
        return "没写喂了哪几只蛊 —— 无处归属"
    try:
        if float(it.get("weight", 0)) <= 0:
            return "weight 必须为正"
    except (TypeError, ValueError):
        return "weight 不是数"
    if it["kind"] == "prediction":
        for f in ("claim", "falsifier"):
            if not str(it.get(f, "")).strip():
                return f"判断缺 {f}"
        if it.get("status") not in STATUSES:
            return f"判断的 status 非法（只能是 {STATUSES}）"
    return None


def load_receipts() -> tuple[list[dict], list[str]]:
    """→ (所有外部条目平铺列表, 警告列表)。

    条目平铺 —— 调用方不必关心它来自几个源。
    """
    items: list[dict] = []
    warns: list[str] = []
    registry, _ = load_registry()

    for s in registry:
        name = s.get("name") or Path(str(s.get("path", "?"))).stem
        if s.get("kind", "receipt") != "receipt":
            warns.append(f"[{name}] kind 不认识，跳过：{s.get('kind')}")
            continue
        path = _resolve(str(s.get("path", "")))
        if not path.exists():
            warns.append(f"[{name}] 回执文件不在，跳过：{path}")
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            warns.append(f"[{name}] 回执读不了，跳过：{type(e).__name__}")
            continue

        seen = set()
        for it in doc.get("items", []):
            why = _shape_ok(it)
            if why:
                warns.append(f"[{name}] 条目 {it.get('key', '?')} 不合规（{why}），跳过")
                continue
            if it["key"] in seen:
                warns.append(f"[{name}] 条目 {it['key']} 在同一个回执里重复，跳过")
                continue
            seen.add(it["key"])
            items.append({**it, "_source": name, "_project": doc.get("project", name)})

    return items, warns


def source_label(src: Path | None) -> str:
    """给输出用的一行来源说明 —— 面板/控制台要能自证跑的是哪一份。"""
    if src is None:
        return "未配置外部源"
    return f"{src.parent.name}/{src.name}" + ("（真实登记）" if src == REAL else "（脱敏示例）")


if __name__ == "__main__":
    reg, src = load_registry()
    items, warns = load_receipts()
    print(f"登记表：{source_label(src)} · {len(reg)} 个源")
    for s in reg:
        print(f"  · {s.get('name', '?')} → {s.get('path')}")
    print(f"\n装载到 {len(items)} 条外部条目：")
    for it in items:
        print(f"  [{it['_source']}] {it['key']}  ({it['kind']}, {it['ts']})")
    if warns:
        print(f"\n{len(warns)} 条警告：")
        for w in warns:
            print(f"  ⚠ {w}")
