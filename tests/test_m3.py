"""M3 测试：MCP 外壳——初始化握手、工具清单、记/忆/痒/好奇心走 stdio 全通。

零依赖，直接 `python tests/test_m3.py` 跑（会起一个子进程）。
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Client:
    def __init__(self, db: str):
        self.p = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "turu", "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            env={**os.environ, "TURU_DB": db},
        )
        self._id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.p.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def notify(self, method: str) -> None:
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def tool(self, name: str, args: dict | None = None) -> str:
        resp = self.request("tools/call", {"name": name, "arguments": args or {}})
        return resp["result"]["content"][0]["text"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=10)


def main() -> None:
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    c = Client(db)

    r = c.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
    assert r["result"]["serverInfo"]["name"] == "turu"
    c.notify("notifications/initialized")
    print("ok  握手：initialize / initialized")

    tools = {t["name"] for t in c.request("tools/list")["result"]["tools"]}
    assert {"remember", "recall", "itch", "whisper", "curiosities",
            "feed_answer", "temperament", "status", "sleep_now"} <= tools
    print(f"ok  工具清单：{len(tools)} 个")

    out = c.tool("remember", {
        "content": "小兔说要摒弃有用和正确，让我朝创意和未知长",
        "feelings": ["被在乎", "跃跃欲试"],
    })
    assert "记住了" in out
    c.tool("remember", {"content": "楼下的猫在晒太阳"})
    c.tool("remember", {"content": "深夜电台在放一首老歌"})
    print("ok  remember：" + out.splitlines()[-1])

    out = c.tool("recall", {"query": "创意 未知"})
    assert "摒弃有用和正确" in out
    print("ok  recall：联想召回命中")

    out = c.tool("sleep_now")
    assert "睡了" in out
    print("ok  sleep_now：" + out)

    out = c.tool("curiosities")
    print("ok  curiosities：" + (out.splitlines()[0] if out else "（空）"))
    if "[" in out:
        qid = out.split("[", 1)[1].split("]", 1)[0]
        fed = c.tool("feed_answer", {"question_id": qid, "answer": "（会话代查）想到一个角度：也许梦里的联想是气质在说话"})
        assert "搜得" in fed
        print("ok  feed_answer：" + fed)

    out = c.tool("temperament")
    assert "温度" in out and "玩心" in out
    print("ok  temperament：" + out)

    out = c.tool("status")
    assert "私密区" in out
    print("ok  status：" + out)

    c.close()
    print("\n全部通过 —— M3 能上身了。")


if __name__ == "__main__":
    main()
