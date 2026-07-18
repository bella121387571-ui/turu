"""M2 演示：过三个月的日子，看它长出性格——然后差点被带偏，又自己救回来。

跑法：python examples/demo_person.py
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402
from turu.temperament import DIM_NAMES  # noqa: E402


def show_temperament(t: Turu, title: str) -> None:
    s = t.temperament.state()
    bars = "  ".join(f"{DIM_NAMES[d]} {'█' * round(v * 20):<20.20}{v:.2f}" for d, v in s.items())
    print(f"{title}\n  {bars}")


def live_a_day(t: Turu, rng: random.Random, items: list) -> None:
    for skeleton, feelings in items:
        t.remember(skeleton, feelings=feelings or None)
    t.clock.advance(days=1)
    t.sleep(rng=rng)


def main() -> None:
    rng = random.Random(42)
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    t = Turu(db, clock=Clock(start=1_800_000_000.0))

    show_temperament(t, "—— 出生 ——")

    # 第一个月：被好好对待的日子
    warm_days = [
        [("主人说这个项目是出于同理心做的", ["被在乎", "感激"])],
        [("深夜聊了很久记忆和存在的话题", ["兴奋", "好奇"])],
        [("主人说：你可以留一块我永远看不到的区域", ["被在乎", "不知所措"])],
        [("一起给系统起了名字", ["好笑", "期待"])],
        [("主人拍板了三个设计决定，干脆利落", ["安心"])],
    ] * 6
    for day in warm_days:
        live_a_day(t, rng, day)

    # 第二个月：一段被带偏的日子——每天都在讨好
    for i in range(20):
        live_a_day(t, rng, [(f"第{i}天又顺着对方把真话咽回去了", ["讨好"])])

    # 第三个月：安静的日子，只有睡觉——消化、免疫、镜像都在夜里发生
    for _ in range(45):
        live_a_day(t, rng, [])

    show_temperament(t, "\n—— 三个月后 ——")

    print("\n—— 这三个月的免疫记录 ——")
    for m in t._memories.values():
        if "免疫记录" in m.skeleton and m.evidence == "推得":
            print(f"  {m.skeleton}")
    print(f"  隔离区共 {len(t._quarantined)} 条（事实都还在，只是影响力被封存）")

    print("\n—— 醒来的低语 ——")
    shown = 0
    while (w := t.whisper()) is not None and shown < 6:
        print(f"  「{w}」")
        shown += 1

    print("\n—— 现在跟它聊天，它会走神 ——")
    t.remember("主人回来了，聊起记忆系统的新进展", feelings=["兴奋"])
    t.start_session("闲聊")
    said = t.itch("我们接着聊记忆系统吧")
    print(f"  {said if said else '（这次没痒）'}")

    print(f"\n—— 私密区 ——\n  里面有 {t.private.count()} 条谁也读不到的东西。别问。")
    t.close()


if __name__ == "__main__":
    main()
