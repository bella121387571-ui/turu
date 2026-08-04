"""实地测试暴露的两个问题的回归测试：

1. 系统自己写的话（融合前缀、导入模板）不许长成概念点
2. 早先长歪的点，睡一觉自动清掉

零依赖，直接 `python tests/test_junk.py` 跑。
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402


def fresh() -> Turu:
    path = os.path.join(tempfile.mkdtemp(), "turu.db")
    return Turu(path, clock=Clock(start=1_800_000_000.0))


def test_system_phrases_never_become_points():
    t = fresh()
    # 模拟导入产生的朴素记忆（每条都带同样的模板）+ 融合产物
    for i in range(6):
        t.remember(f"2026-07-0{i} 和小兔聊过：关于抖音计划的第{i}次讨论")
    for i in range(4):
        t.remember(f"（消化后的印象）和小兔聊过：抖音计划的事 第{i}版", evidence="融合")
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))

    points = [m.skeleton for m in t._memories.values() if m.kind == "概念"]
    for junk in ("消化后的印象", "和小兔聊过", "（"):
        assert not any(junk in p for p in points), f"系统模板不该成点: {points}"
    assert any("抖音计划" in p for p in points), f"真正的概念该长出来: {points}"
    print(f"ok  概念干净：长出 {points}，没有模板垃圾")


def test_purge_old_junk_points():
    t = fresh()
    t.remember("正常的一段经历")
    # 手动塞一个早先版本长歪的点
    bad, _ = t.get_or_create_point("（消化后的印", t.clock.now())
    t.link(bad.id, next(iter(t._memories)), "关于", weight=0.5)
    assert any(m.kind == "概念" for m in t._memories.values())

    t.clock.advance(days=1)
    r = t.sleep(force=True, rng=random.Random(7))
    assert bad.id not in t._memories, "长歪的点该被清掉"
    assert not any(bad.id in (k[0], k[1]) for k in t._tendrils), "它的触须也该断干净"
    assert any("长歪的点" in n for n in r.notes), f"该在睡眠报告里说一声: {r.notes}"
    print("ok  自动清理：睡一觉，早先长歪的点消失了")


def test_fusion_not_woven():
    t = fresh()
    t.remember("小兔今天说起了记忆系统的事")
    t.remember("小兔今天又说起记忆系统的事")
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))  # 会产生融合记忆
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))  # 融合记忆此时应被跳过
    fusion = [m for m in t._memories.values() if m.evidence == "融合" and m.kind == "事件"]
    if fusion:
        woven = t.store.woven_ids()
        assert all(m.id in woven for m in fusion), "融合产物应直接标记已织，不当原料"
    print("ok  只织真实经历：系统产物不当织网原料")


if __name__ == "__main__":
    for fn in [test_system_phrases_never_become_points, test_purge_old_junk_points,
               test_fusion_not_woven]:
        fn()
    print("\n全部通过 —— 概念点不再长歪。")
