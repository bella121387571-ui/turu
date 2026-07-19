"""手机近况页测试：能看、令牌拦人、真的只读。

零依赖，直接 `python tests/test_web.py` 跑。
"""

import http.client
import os
import random
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402
from turu.webview import Handler, render  # noqa: E402


def main() -> None:
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    t = Turu(db, clock=Clock(start=1_800_000_000.0))
    t.remember("主人说想在手机上也看到我的近况", feelings=["被在乎"])
    t.remember("楼下的猫在晒太阳")
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))
    whispers_before = t.store.meta_get("whispers")
    t.close()

    page = render(db)
    assert "它的近况" in page and "性子" in page and "手机上也看到" in page
    assert "私密区" in page and "只有数量" in page, "私密区永远只报数量"
    print("ok  页面：性子/身体/低语/记忆都在，私密区只报数量")

    from turu.store import Store
    s = Store(db)
    assert s.meta_get("whispers") == whispers_before, "只读：偷看不许取走低语"
    s.meta_set("web_token", "testtoken")
    s.close()

    Handler.token = "testtoken"
    Handler.db_path = db
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", "/testtoken")
    resp = conn.getresponse()
    body = resp.read().decode("utf-8")
    assert resp.status == 200 and "它的近况" in body
    print("ok  访问：正确令牌 200")

    conn.request("GET", "/wrongtoken")
    assert conn.getresponse().status == 404
    conn.request("GET", "/")
    assert conn.getresponse().status == 404
    print("ok  拦截：错误令牌/无令牌 404")

    server.shutdown()
    print("\n全部通过 —— 手机能看它的近况了。")


if __name__ == "__main__":
    main()
