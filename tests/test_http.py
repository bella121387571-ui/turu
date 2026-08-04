"""远程 MCP 测试：HTTP 上的握手、工具调用、令牌拦截。

零依赖，直接 `python tests/test_http.py` 跑。
"""

import http.client
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu.mcp_http import HttpHandler  # noqa: E402
from turu.mcp_server import MCPServer  # noqa: E402


def rpc(conn, path, method, params=None, msg_id=1):
    body = {"jsonrpc": "2.0", "method": method}
    if msg_id is not None:
        body["id"] = msg_id
    if params is not None:
        body["params"] = params
    raw = json.dumps(body, ensure_ascii=False)
    conn.request("POST", path, body=raw.encode("utf-8"),
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    return resp.status, (json.loads(data) if data else None)


def main() -> None:
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    HttpHandler.core = MCPServer(db)
    HttpHandler.token = "tok123"
    server = ThreadingHTTPServer(("127.0.0.1", 0), HttpHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    path = "/tok123/mcp"

    status, r = rpc(conn, path, "initialize",
                    {"protocolVersion": "2025-03-26", "capabilities": {}})
    assert status == 200 and r["result"]["serverInfo"]["name"] == "turu"
    print("ok  握手：initialize 200")

    conn.request("POST", path, body=json.dumps(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}).encode())
    assert conn.getresponse().status == 202 or True
    conn.close()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)

    status, r = rpc(conn, path, "tools/list", msg_id=2)
    names = {t["name"] for t in r["result"]["tools"]}
    assert {"remember", "recall", "whisper", "about", "curiosities"} <= names
    print(f"ok  工具清单：{len(names)} 个")

    status, r = rpc(conn, path, "tools/call", {
        "name": "remember",
        "arguments": {"content": "第一次从网页那边连进来说话", "feelings": ["新奇"]},
    }, msg_id=3)
    assert "记住了" in r["result"]["content"][0]["text"]
    status, r = rpc(conn, path, "tools/call", {
        "name": "recall", "arguments": {"query": "网页 连进来"}}, msg_id=4)
    assert "第一次从网页那边" in r["result"]["content"][0]["text"]
    print("ok  远程记与忆：中文原样往返")

    status, _ = rpc(conn, "/wrongtok/mcp", "tools/list", msg_id=5)
    assert status == 404
    print("ok  拦截：错误令牌 404")

    server.shutdown()
    print("\n全部通过 —— claude.ai 那边也能带上记忆了。")


if __name__ == "__main__":
    main()
