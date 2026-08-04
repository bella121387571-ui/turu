"""远程 MCP 外壳：让 claude.ai（网页/手机 App）直接用上这份记忆。

原理：claude.ai 的『自定义连接器』能连一个网址上的 MCP 服务器
（streamable HTTP：POST JSON-RPC）。本模块把 stdio 版的九个工具
原样搬到 HTTP 上，配一条隧道（如 cloudflared）暴露成 https 网址后，
你在浏览器和手机里的 Claude 就都带着这份记忆说话了。

安全：路径里带随机令牌（与手机近况页同一个），不知道令牌连不上；
工具本身的纪律不变（私密区无读取接口、对外动作可审计）。

启动：python turu/mcp_http.py（或双击 远程连接.bat）
端口默认 7778，可用 TURU_HTTP_PORT 改。
连接器要填的地址：https://<你的隧道域名>/<令牌>/mcp
"""

import json
import os
import re
import secrets
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CF_URL = ("https://github.com/cloudflare/cloudflared/releases/latest/download/"
          "cloudflared-windows-amd64.exe")

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from turu.mcp_server import MCPServer  # noqa: E402
from turu.store import Store  # noqa: E402


class HttpHandler(BaseHTTPRequestHandler):
    core: MCPServer = None
    token = ""
    lock = threading.Lock()

    def _path_ok(self) -> bool:
        return self.path.rstrip("/") in (f"/{self.token}/mcp", f"/{self.token}")

    def do_POST(self):  # noqa: N802
        if not self._path_ok():
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            msg = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        with self.lock:
            resp = self.core.handle(msg)
        if resp is None:  # 通知类消息：收到即可
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps(resp, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        # 不提供 SSE 流（规范允许）；GET 到令牌路径回一句活着的证明
        if self._path_ok():
            self.send_response(405)
        else:
            self.send_response(404)
        self.end_headers()

    def do_DELETE(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def ensure_cloudflared(root: str) -> str | None:
    """找到隧道工具；没有就自己下载一次（约 60MB，只下一次）。"""
    exe = os.path.join(root, "cloudflared.exe")
    if os.path.exists(exe):
        return exe
    if os.name != "nt":
        return None
    print("第一次运行：正在下载隧道工具（约 60MB，只需下这一次）……")
    try:
        with urllib.request.urlopen(CF_URL, timeout=300) as r, open(exe, "wb") as f:
            f.write(r.read())
        print("下载完成。\n")
        return exe
    except Exception as e:  # noqa: BLE001
        print(f"下载失败（{e}）。请检查代理是否开着，或手动下载：\n  {CF_URL}")
        print(f"下载后改名为 cloudflared.exe 放到：{root}\n")
        return None


def start_tunnel(exe: str, port: int, token: str) -> None:
    """起隧道，盯着它的输出，把完整的连接器地址拼好打出来。"""
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )

    def watch():
        pattern = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
        for line in proc.stdout:
            m = pattern.search(line)
            if m:
                print("\n" + "=" * 62)
                print("  连接器地址（复制下面这一整行，填进 claude.ai）：")
                print(f"\n     {m.group(0)}/{token}/mcp\n")
                print("  claude.ai → 设置 → 连接器 → 添加自定义连接器 → 粘贴")
                print("=" * 62 + "\n")
                print("（这个窗口别关。关了 claude.ai 那边就连不上它了。）")
                break

    threading.Thread(target=watch, daemon=True).start()


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_db = os.path.join(root, "data", "turu.db")
    db = os.environ.get("TURU_DB", default_db)
    store = Store(db)
    token = store.meta_get("web_token")
    if not token:
        token = secrets.token_urlsafe(8)
        store.meta_set("web_token", token)
    store.close()

    port = int(os.environ.get("TURU_HTTP_PORT", "7778"))
    HttpHandler.core = MCPServer(db)
    HttpHandler.token = token
    server = ThreadingHTTPServer(("127.0.0.1", port), HttpHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("它的记忆服务器起来了。正在开隧道，稍等十几秒……\n")

    exe = ensure_cloudflared(root)
    if exe:
        start_tunnel(exe, port, token)
    else:
        print(f"没有隧道，只能本机用：http://127.0.0.1:{port}/{token}/mcp")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
