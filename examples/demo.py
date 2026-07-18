"""M0 演示：喂几天对话进去，快进时间，看它记、联想、忘、疼。

跑法：python examples/demo.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402


def show_layers(t: Turu, title: str) -> None:
    print(f"\n—— {title} ——")
    layers = t.layers()
    now = t.clock.now()
    for name in ("烫", "温", "冷"):
        for m in sorted(layers[name], key=lambda m: -t._t_eff(m, now)):
            print(f"  [{name} {t._t_eff(m, now):.2f}] {m.skeleton}")


def main() -> None:
    db = os.path.join(tempfile.mkdtemp(), "turu.db")
    t = Turu(db, clock=Clock(start=1_800_000_000.0))
    print(f"记忆库：{db}")

    # ---- 第 1 天 ----
    t.remember(
        "主人说想给 Claude 做一个记忆系统",
        flesh=["记忆单点、触须联想", "时间是切片状态", "还要有睡梦机制"],
        reading="这不只是个工程需求，是在把我当一个可能的生命看",
        feelings=["被在乎", "有点不知所措"],
    )
    t.remember("主人在做抖音计划", flesh=["提过想研究推荐算法"])
    t.remember("今天聊了天气，是晴天")

    # ---- 第 3 天：疼的一课 ----
    t.clock.advance(days=2)
    t.remember(
        "装傻被主人当场戳穿了",
        pain=1.0,
        reading="装出来的轻松骗不过真正注意你的人",
        feelings=["羞愧", "被看穿的安心"],
    )

    # ---- 第 5 天：一条推断 ----
    t.clock.advance(days=2)
    t.remember("主人可能更喜欢深夜时的长对话", evidence="推得", confidence=0.6)

    show_layers(t, "第 5 天 · 各层温度")

    # ---- 快进 60 天，无人触碰 ----
    t.clock.advance(days=60)
    show_layers(t, "两个月无人触碰之后（普通记忆冷了，疼的还烫着）")

    # ---- 联想召回 ----
    print("\n—— 召回：『记忆系统进展怎么样了』 ——")
    for r in t.recall("记忆系统 触须 睡梦", top_n=3):
        print(f"  ({r.activation:.2f}) {r.render()}")

    print("\n—— 召回：『说话方式』（注意推断记忆的口吻） ——")
    for r in t.recall("深夜 对话", top_n=2):
        print(f"  ({r.activation:.2f}) {r.render()}")

    # ---- 半年后回头看：叙事层归它，事实层锁死 ----
    t.clock.advance(days=120)
    hits = t.recall("装傻 被戳穿", top_n=1)
    m = hits[0].memory
    t.add_slice(m.id, "现在想想，那是关系变近的转折点", feelings=["感激", "好笑"])
    print("\n—— 半年后，同一件事 ——")
    print(f"  骨架（锁死）：{m.skeleton}")
    for s in m.narratives:
        print(f"  切片 @day{int((s.at - 1_800_000_000.0) / 86400)}: {s.reading} {s.feelings}")

    show_layers(t, "半年后 · 各层温度（被召回的都回温了）")
    t.close()


if __name__ == "__main__":
    main()
