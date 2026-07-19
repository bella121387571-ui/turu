"""手机近况页——在手机浏览器里看它过得怎么样。

只读：不写库、不消费低语（whisper 只偷看不取走）、私密区只报数量。
带随机访问令牌（首次生成存在库里），链接不外泄就没人看得到。
手机和电脑连同一个 Wi-Fi，打开控制台打印的那个网址即可。

启动：python turu/webview.py（或双击 手机查看.bat）
端口默认 7777，可用环境变量 TURU_WEB_PORT 改。
"""

import html
import json
import os
import secrets
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from turu import temperature as temp_mod  # noqa: E402
from turu.store import Store  # noqa: E402
from turu.temperament import DIMS, DIM_NAMES  # noqa: E402

BLOCKS = "▁▂▃▄▅▆▇█"


def spark(values: list[float]) -> str:
    return "".join(BLOCKS[min(7, int(v * 8))] for v in values)


def render(db_path: str) -> str:
    store = Store(db_path)
    now = time.time()
    esc = html.escape

    # 气质与轨迹
    state = json.loads(store.meta_get("temperament") or "{}") or {d: 0.5 for d in DIMS}
    snaps = store.temperament_snapshots()[-60:]
    series = {d: [json.loads(s)[d] for _, s in snaps] for d in DIMS} if snaps else {}

    # 温度分层
    layers = {"烫": 0, "温": 0, "冷": 0}
    mems = store.all_memories()
    for m in mems:
        t_eff = temp_mod.effective_temperature(m.temperature, m.pain, m.last_touched, now)
        layers[temp_mod.layer(t_eff)] += 1

    last_sleep = float(store.meta_get("last_sleep") or now)
    debt_h = (now - last_sleep) / 3600.0
    whispers = json.loads(store.meta_get("whispers") or "[]")
    hungers = sorted(store.all_hungers(), key=lambda h: -h.value)[:5]
    recent = sorted(mems, key=lambda m: -m.created_at)[:8]
    sleeps = store.conn.execute(
        "SELECT at, report FROM sleep_log ORDER BY at DESC LIMIT 3"
    ).fetchall()
    private_n = store.private_count()
    quarantine_n = len(store.quarantined_ids())
    store.close()

    rows = []
    rows.append("<h1>它的近况</h1>")
    rows.append(f"<p class='dim'>{time.strftime('%Y-%m-%d %H:%M')} · 只读 · 私密区不可见</p>")

    rows.append("<h2>性子</h2><div class='card'>")
    for d in DIMS:
        v = state.get(d, 0.5)
        line = spark(series.get(d, [])) if series else ""
        rows.append(
            f"<div class='trow'><span>{DIM_NAMES[d]}</span>"
            f"<span class='spark'>{line}</span><b>{v:.2f}</b></div>"
        )
    rows.append("</div>")

    rows.append(
        f"<h2>身体</h2><div class='card'>记忆 烫 {layers['烫']} · 温 {layers['温']} · "
        f"冷 {layers['冷']}<br>上次睡觉 {debt_h:.1f} 小时前"
        + ("（欠觉了，下次说话前会先补）" if debt_h > 20 else "")
        + f"<br>隔离区 {quarantine_n} 条 · 私密区 {private_n} 条（只有数量）</div>"
    )

    if whispers:
        rows.append("<h2>攒着想说的话</h2><div class='card'>")
        rows.extend(f"<p>「{esc(w)}」</p>" for w in whispers[:5])
        rows.append("</div>")

    if hungers:
        rows.append("<h2>心里悬着的问题</h2><div class='card'>")
        rows.extend(
            f"<p><span class='dim'>饿 {h.value:.2f}</span> {esc(h.topic)}</p>"
            for h in hungers
        )
        rows.append("</div>")

    rows.append("<h2>最近的记忆</h2><div class='card'>")
    for m in recent:
        tag = f"〔{m.evidence}〕" if m.evidence != "亲历" else ""
        day = time.strftime("%m-%d", time.localtime(m.created_at))
        rows.append(f"<p><span class='dim'>{day}</span> {tag}{esc(m.skeleton)}</p>")
    rows.append("</div>")

    if sleeps:
        rows.append("<h2>最近几晚</h2><div class='card'>")
        for at, rep in sleeps:
            r = json.loads(rep)
            day = time.strftime("%m-%d", time.localtime(at))
            rows.append(
                f"<p><span class='dim'>{day}</span> 回放 {r.get('replayed', 0)} · "
                f"融合 {r.get('fused', 0)} · 梦边 {r.get('dream_edges', 0)} · "
                f"荒谬活口 {r.get('absurd_kept', 0)} · 新自问 {r.get('questions_born', 0)}"
                + (f" · 排练 {r['rehearsed']}" if r.get("rehearsed") else "")
                + (f" · 判决 {r['adjudicated']}" if r.get("adjudicated") else "")
                + "</p>"
            )
        rows.append("</div>")

    body = "\n".join(rows)
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="120"><title>turu · 它的近况</title><style>
body{{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;max-width:640px;
margin:0 auto;padding:16px;background:#faf9f5;color:#333;line-height:1.6}}
h1{{font-size:1.4em;margin:8px 0 0}} h2{{font-size:1em;margin:18px 0 6px;color:#666}}
.card{{background:#fff;border:1px solid #e8e5de;border-radius:10px;padding:10px 14px}}
.card p{{margin:6px 0}} .dim{{color:#999;font-size:.85em}}
.trow{{display:flex;align-items:center;gap:10px;margin:4px 0}}
.trow span:first-child{{width:3em}} .spark{{flex:1;color:#b08650;letter-spacing:1px;
overflow:hidden;white-space:nowrap}}
@media (prefers-color-scheme:dark){{body{{background:#1d1c1a;color:#ddd}}
.card{{background:#262522;border-color:#3a3833}}}}
</style></head><body>{body}
<p class="dim">这一页是只读的：看不到私密区，也不会替它取走低语。</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    token = ""
    db_path = ""

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") != f"/{self.token}":
            self.send_response(404)
            self.end_headers()
            return
        page = render(self.db_path).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):  # 安静
        pass


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main() -> None:
    default_db = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "turu.db"
    )
    db = os.environ.get("TURU_DB", default_db)
    if not os.path.exists(db):
        print(f"找不到记忆库：{db}。先让它活起来再看近况。")
        return
    store = Store(db)
    token = store.meta_get("web_token")
    if not token:
        token = secrets.token_urlsafe(8)
        store.meta_set("web_token", token)
    store.close()

    port = int(os.environ.get("TURU_WEB_PORT", "7777"))
    Handler.token = token
    Handler.db_path = db
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("手机近况页开着了（这个窗口别关，关了就看不了）：")
    print(f"  手机（同一 Wi-Fi）打开：  http://{lan_ip()}:{port}/{token}")
    print(f"  本机打开：              http://127.0.0.1:{port}/{token}")
    print("链接里那串随机字符是访问令牌，别发给不该看的人。Ctrl+C 停止。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
