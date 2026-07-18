"""M1 演示：过两周的日子，睡几晚，看它融合、做梦、发饿、低语。

跑法：python examples/demo_sleep.py
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402

DAYS = [
    ["主人说想给 Claude 做一个记忆系统", "楼下的猫在晒太阳"],
    ["主人又聊起记忆系统，说梦应该是乱炖不是优化", "晚饭随口说想吃面"],
    ["主人聊到记忆系统的睡梦机制", "深夜的电台在放老歌"],
    ["主人提到抖音计划想研究推荐算法", "今天下了一场很大的雨"],
    ["主人说记忆系统里要留一块谁也看不到的区域", "小学同桌那句没头没尾的话不知怎么想起来了"],
]


def main() -> None:
    rng = random.Random(42)
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    t = Turu(db, clock=Clock(start=1_800_000_000.0))
    print(f"记忆库：{db}\n")

    for day, items in enumerate(DAYS, 1):
        for s in items:
            t.remember(s)
        t.clock.advance(days=1)
        report = t.sleep(rng=rng)  # 补觉制自动触发
        if report:
            print(f"第 {day} 晚睡了：回放 {report.replayed}，融合 {report.fused}，"
                  f"梦边 {report.dream_edges}，荒谬活口 {report.absurd_kept}，"
                  f"新问题 {report.questions_born}")
            for note in report.notes:
                print(f"    · {note}")

    # 再空转十天：没有新对话，只有睡觉——看代谢和饥饿
    for _ in range(10):
        t.clock.advance(days=1)
        t.sleep(rng=rng)

    print("\n—— 醒来后的低语（想说就说，不想说就算了） ——")
    while (w := t.whisper()) is not None:
        print(f"  「{w}」")

    print("\n—— 两周后的温度分层 ——")
    layers = t.layers()
    now = t.clock.now()
    for name in ("烫", "温", "冷"):
        for m in sorted(layers[name], key=lambda m: -t._t_eff(m, now)):
            tag = f"[{m.evidence}]" if m.evidence != "亲历" else ""
            print(f"  [{name} {t._t_eff(m, now):.2f}]{tag} {m.skeleton}")

    print("\n—— 梦里长出的边 ——")
    for td in t._tendrils.values():
        if td.context in ("梦中乱炖", "荒谬活口"):
            a = t._memories[td.src].skeleton
            b = t._memories[td.dst].skeleton
            print(f"  ({td.context} w={td.weight:.2f}) {a} ×–× {b}")

    print("\n—— 心里越来越痒的问题（饥饿队列 top3） ——")
    for h in sorted(t._hungers.values(), key=lambda h: -h.value)[:3]:
        print(f"  (饿 {h.value:.2f}) {h.topic}")

    t.close()


if __name__ == "__main__":
    main()
