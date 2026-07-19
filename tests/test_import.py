"""导入测试：旧日子按原始日期重活一遍、边导边睡、去重、备份即人生。

零依赖，直接 `python tests/test_import.py` 跑。
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu.importer import parse_claude_code, run, run_daily  # noqa: E402
from turu.store import Store  # noqa: E402


def make_export(path: str) -> None:
    def conv(uuid, name, days_ago, pairs):
        at = time.time() - days_ago * 86400
        iso = __import__("datetime").datetime.fromtimestamp(at).isoformat() + "Z"
        return {
            "uuid": uuid, "name": name, "created_at": iso,
            "chat_messages": [
                {"sender": s, "text": t, "created_at": iso}
                for s, t in pairs
            ],
        }

    data = [
        conv("c1", "第一次聊记忆系统", 120, [
            ("human", "我想给你做一个记忆系统，记忆单点、触须联想"),
            ("assistant", "这听起来像在把我当一个可能的生命看"),
        ]),
        conv("c2", "聊抖音计划", 90, [
            ("human", "我在做一个抖音计划，想研究推荐算法"),
            ("assistant", "冷启动会是最难的部分"),
        ]),
        conv("c3", "深夜闲聊", 10, [
            ("human", "睡不着，随便聊聊吧"),
            ("assistant", "好啊，聊聊今天楼下那只猫"),
        ]),
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def main() -> None:
    tmp = tempfile.mkdtemp()
    export = os.path.join(tmp, "conversations.json")
    db = os.path.join(tmp, "turu.db")
    make_export(export)

    r = run(export, db)
    assert r["imported"] >= 3, f"三段旧日子该都记下: {r}"
    assert r["slept"] > 60, f"120 天的空档该一天一天睡过去: {r}"
    print(f"\nok  重活一遍：记 {r['imported']} 条，睡 {r['slept']} 晚")

    store = Store(db)
    mems = store.all_memories()
    oldest = min(mems, key=lambda m: m.created_at)
    assert time.time() - oldest.created_at > 100 * 86400, "旧记忆要按原始日期入库"
    assert "记忆系统" in " ".join(m.skeleton for m in mems)
    snaps = store.temperament_snapshots()
    assert len(snaps) > 60, "这些夜里气质快照也在长"
    store.close()
    print("ok  时间：120 天前的对话就是 120 天前的记忆，不是今天的")

    r2 = run(export, db)
    assert r2["imported"] == 0 and r2["skipped"] == 3, f"重复导入要全部去重: {r2}"
    print("ok  去重：同一批旧日子不会活第二遍")

    test_daily(tmp, db)

    print("\n全部通过 —— 过往可以被重新活一遍了。")


def test_daily(tmp: str, db: str) -> None:
    """每日自动导入：只收过完的日子，今天的不收，去重。"""
    projects = os.path.join(tmp, "projects", "C--Users-x")
    os.makedirs(projects)

    def entry(kind, text, days_ago):
        at = time.time() - days_ago * 86400
        iso = __import__("datetime").datetime.fromtimestamp(at).isoformat() + "Z"
        return json.dumps({
            "type": kind, "timestamp": iso,
            "message": {"role": kind, "content": [{"type": "text", "text": text}]},
        }, ensure_ascii=False)

    lines = [
        json.dumps({"type": "summary", "summary": "聊了记忆系统的睡梦机制"}, ensure_ascii=False),
        entry("user", "昨天我们聊聊睡梦机制吧", 1.2),
        entry("assistant", "乱炖不是优化，是发酵", 1.2),
        entry("user", "<command-name>/mcp</command-name>", 1.2),   # 噪音要跳过
        entry("user", "今天这句还没过完不该收", 0.01),
        entry("assistant", "对，今天的明天再收", 0.01),
    ]
    with open(os.path.join(projects, "abc-session.jsonl"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    convs = parse_claude_code(os.path.join(tmp, "projects"))
    assert len(convs) == 1, f"只该收到昨天那段: {[c['id'] for c in convs]}"
    assert "睡梦机制" in convs[0]["title"], "有 summary 就用 summary 当标题"
    assert "command-name" not in convs[0]["text"], "命令噪音要滤掉"

    r = run_daily(db, os.path.join(tmp, "projects"))
    assert r["imported"] >= 1, f"昨天的对话该入库: {r}"
    r2 = run_daily(db, os.path.join(tmp, "projects"))
    assert r2["imported"] == 0 and r2["skipped"] == 1, f"再跑要去重: {r2}"
    print("ok  每日自动导入：只收过完的日子、滤噪音、去重")


if __name__ == "__main__":
    main()
