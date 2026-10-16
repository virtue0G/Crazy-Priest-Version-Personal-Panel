"""网页壳 —— 用标准库起一个本地面板，零新依赖。

设计原则（与 SKILL.md 一致）：
  · 网页壳只加「可点的壳」，不改事实层。关掉它，命令行的东西一样跑。
  · 抽取是 AI 的判断活，网页做不了——所以记录框只负责「收」，不做「判」。
  · 确认证据是「人」的动作，网页只提供入口，不代替人做决定。

用法：
    python web.py            # http://127.0.0.1:8765
    python web.py 9000       # 换端口
"""
import json
import re
import sys
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from db import connect, confirm_evidence, feed_gu, record_heart, set_evidence_alloc
import render


def _same_alloc(con, eid: int, alloc) -> bool:
    """提交的分配和库里现有的，是不是同一个。

    用来区分「改成了别的」和「原样提交」—— 只有前者才算人的一次决定。
    """
    cur = con.execute(
        "SELECT d.name n, ed.weight w FROM evidence_dao ed JOIN daos d ON d.id=ed.dao_id "
        "WHERE ed.evidence_id=?", (eid,)).fetchall()
    a = {(r["n"], round(float(r["w"]), 6)) for r in cur}
    b = {(n, round(float(w), 6)) for n, w in alloc}
    return a == b


def _parse_alloc(raw: str, dao_names: set):
    """「炼道 1 · 星道 0.5」→ [('炼道',1.0), ('星道',0.5)]。

    任何一段不合法就返回 None，表示**保持原分配**。
    跟 `_form()` 的「宁可拒收，不入库」同一个精神：宁可不改，不可乱改 ——
    解析一半就写库，会把一条证据的道痕悄悄改错，而面板上看不出来。
    """
    if not raw.strip():
        return None
    out = []
    for seg in re.split(r"[·、,，;；]", raw):
        bits = seg.split()
        if len(bits) != 2:
            return None
        name, val = bits
        if name not in dao_names:
            return None
        try:
            w = float(val)
        except ValueError:
            return None
        if w < 0:
            return None
        out.append((name, w))
    return out or None

ROOT = Path(__file__).parent.parent
INBOX = ROOT / "data" / "收件箱.md"
DEFAULT_PORT = 8765

# 端口一律由调用方给，**不在导入时读 sys.argv**。
# 原来这里写的是 `PORT = int(sys.argv[1])`，于是 `python run.py web`
# 在 `import web` 那一刻就把 "web" 拿去 int()，直接 ValueError ——
# 这条命令从写下那天起就没跑起来过，而 SKILL.md 里一直写着它。


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):        # 别把每个请求都刷到控制台
        pass

    def _send(self, body: bytes, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")   # 永远看最新数据
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            # 每次访问都重新渲染 —— 数据变了刷新即见，不用手动跑命令
            html = render.render(web=True).read_text(encoding="utf-8")
            self._send(html.encode("utf-8"))
        elif path == "/status":
            con = connect()
            # 只算已确认的。原来把 confirmed=1 写在 LEFT JOIN 的 ON 里 ——
            # 那样未确认的证据**照样被算进 SUM**（LEFT JOIN 不会因为 e 没匹配上就丢掉这行），
            # 于是这个接口报的数比 `run.py status` 的「已确认」列偏大，两边打架。
            # 要过滤就得放进 SUM 里用 CASE，不能放进 ON。
            rows = con.execute("""
                SELECT d.name, ROUND(COALESCE(SUM(CASE WHEN e.confirmed=1
                                                       THEN ed.weight END),0),1) m
                FROM daos d LEFT JOIN evidence_dao ed ON ed.dao_id=d.id
                LEFT JOIN evidence e ON e.id=ed.evidence_id
                WHERE d.active=1 GROUP BY d.id ORDER BY m DESC""").fetchall()
            self._send(json.dumps([dict(r) for r in rows], ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(b"404", code=404)

    def _form(self):
        """解析表单，只认 UTF-8——因为本页自己就是 UTF-8，浏览器必按此提交。

        踩过的坑：非 UTF-8 客户端提交时，GBK 字节如 CD F8 **能**被 utf-8 解得出来
        （落成科普特字母之类的乱码），并不抛异常，于是乱码被原样写进 data/，
        污染事实层。所以这里不做「换编码再试」——那只会把乱码合法化。
        宁可拒收，也不入库。
        """
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            form = urllib.parse.parse_qs(raw.decode("utf-8"), strict_parsing=False)
        except UnicodeDecodeError:
            return {}
        # 第二步拦截：百分号转义体是纯 ASCII，解码不会报错，真正的坏事发生在
        # unquote 里——非 UTF-8 字节被换成 U+FFFD 替换符。见到它，说明来源编码不对，
        # 收下就是收下一行乱码。
        if any("�" in v for vs in form.values() for v in vs):
            return {}
        return form

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        form = self._form()

        if path == "/confirm":
            ids = [int(i) for i in form.get("id", [])]
            con = connect()
            # 调权只针对被勾选的条目；改不动的（手写证据）根本没有那个输入框。
            # 先改分配、再确认 —— 顺序反了会让「确认后才计道痕」的那一刻用的是旧分配。
            names = {r["name"] for r in con.execute("SELECT name FROM daos")}
            for eid in ids:
                raw = (form.get(f"alloc_{eid}", [""])[0] or "").strip()
                alloc = _parse_alloc(raw, names)
                # **只在真的改了时才写。** 每次提交都写一遍的话，光点个「确认」
                # 也会把分配标成「人改过」（set_evidence_alloc 默认 edited=True），
                # 于是外部回执以后改提议就再也推不动这条了 —— 标记就失去了意义。
                if alloc and not _same_alloc(con, eid, alloc):
                    set_evidence_alloc(con, eid, alloc)
            if ids:
                confirm_evidence(con, ids)
            self._redirect("/")

        elif path == "/feed":
            # 「炼了」—— 只记日期，饥饱由 derive_gu_state 从日期推，不在这里写死状态。
            gid = (form.get("gu_id", [""])[0] or "").strip()
            if gid.isdigit():
                st = feed_gu(connect(), int(gid))
                print(f"✓ 已记一次炼 · 蛊 #{gid} → {st}", flush=True)
            self._redirect("/")

        elif path == "/heart":
            # 心力自述：不记也行（面板会按记录推一个下限），记了就覆盖推演。
            raw = (form.get("capacity", [""])[0] or "").strip()
            if raw.isdigit():
                record_heart(connect(), int(raw),
                             (form.get("horizon", ["week"])[0] or "week"),
                             (form.get("mood", [""])[0] or "").strip())
                print(f"✓ 已记心力：{raw} 件", flush=True)
            self._redirect("/")

        elif path == "/record":
            text = (form.get("text", [""])[0] or "").strip()
            if text:
                INBOX.parent.mkdir(parents=True, exist_ok=True)
                with INBOX.open("a", encoding="utf-8") as f:
                    f.write(f"- {date.today().isoformat()} {text}\n")
            self._redirect("/")

        else:
            self._send(b"404", code=404)

    def _redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()


class Server(HTTPServer):
    # 关键：Windows 下允许多个进程同时绑同一端口，于是「起了一个新的」其实
    # 是「新旧一起在服务」，请求被轮流转发，改了代码却看到旧行为——极难排查。
    # 关掉复用，第二个实例就会直接报错退出。
    allow_reuse_address = False


def serve(port: int = DEFAULT_PORT):
    try:
        srv = Server(("127.0.0.1", port), Handler)
    except OSError:
        print(f"✗ 端口 {port} 已被占用——多半是上一次的面板还在跑。", flush=True)
        print(f"  先停掉它，或换个端口：python run.py web 8766", flush=True)
        return
    print(f"✓ 修行面板已起：http://127.0.0.1:{port}", flush=True)
    print("  数据变了刷新即见；Ctrl+C 停。", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    # 直接跑本文件时，端口从命令行拿；`python run.py web [端口]` 走的是另一条路。
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT)
