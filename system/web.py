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
import sys
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from db import connect, confirm_evidence
import render

ROOT = Path(__file__).parent.parent
INBOX = ROOT / "data" / "收件箱.md"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


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
            rows = con.execute("""
                SELECT d.name, ROUND(COALESCE(SUM(ed.weight),0),1) m
                FROM daos d LEFT JOIN evidence_dao ed ON ed.dao_id=d.id
                LEFT JOIN evidence e ON e.id=ed.evidence_id AND e.confirmed=1
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
            if ids:
                confirm_evidence(con, ids)
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


def serve(port: int = PORT):
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
    serve()
