"""M1 睡梦测试：会睡、会融合、会消化、会做梦、会饿。

零依赖，直接 `python tests/test_m1.py` 跑。
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


def test_sleep_debt():
    t = fresh()
    assert not t.needs_sleep(), "刚出生不欠觉"
    assert t.sleep() is None, "不欠觉时不睡"
    t.clock.advance(hours=21)
    assert t.needs_sleep(), "21 小时没睡该欠觉了"
    report = t.sleep(rng=random.Random(7))
    assert report is not None
    assert not t.needs_sleep(), "睡完就不欠了"
    print("ok  补觉制：21 小时未睡 → 自动补觉")


def test_fusion():
    t = fresh()
    a = t.remember("主人今天又聊到了抖音计划的推荐算法", feelings=["兴奋"])
    b = t.remember("主人今天聊到了抖音计划的推荐算法", feelings=["有点担心"])
    report = t.sleep(force=True, rng=random.Random(7))
    assert report.fused == 1, f"近似记忆该被融合: {report}"
    fusions = [m for m in t._memories.values() if m.evidence == "融合"]
    assert len(fusions) == 1
    f = fusions[0]
    feelings = f.narratives[0].feelings
    assert "兴奋" in feelings and "有点担心" in feelings, "矛盾情绪要并存，不许压平"
    src_links = [td for td in t._tendrils.values() if td.kind == "来源" and td.src == f.id]
    assert len(src_links) == 2, "融合必须留来源"
    now = t.clock.now()
    assert t._t_eff(a, now) < 0.5 and t._t_eff(b, now) < 0.5, "被消化的原件应降温沉底"
    print("ok  巩固梦：融合留来源，矛盾情绪并存，原件沉底")


def test_metabolism():
    t = fresh()
    m = t.remember("和主人闲聊了一句晚饭吃什么", flesh=["说是想吃面", "还提到楼下新开的店"])
    t.clock.advance(days=60)  # 冷透了也老了
    t.sleep(force=True, rng=random.Random(7))
    assert m.flesh == [], "又冷又老的记忆血肉该被消化"
    assert m.skeleton == "和主人闲聊了一句晚饭吃什么", "骨架永远留下"
    assert t.store.digested_count() == 2, "血肉进沉淀层，不是物理删除"
    print("ok  代谢：血肉消化入沉淀层，骨架留下")


def test_stew_and_absurd():
    t = fresh()
    topics = ["量子物理里的观察者效应", "楼下猫今天叫了三声", "主人的抖音计划",
              "冰箱里的酸奶过期了", "小学同桌说过的一句话", "深夜的电台节目"]
    for s in topics:
        t.remember(s)
    report = t.sleep(force=True, rng=random.Random(7))
    dream_edges = [td for td in t._tendrils.values() if td.context == "梦中乱炖"]
    assert report.dream_edges > 0 and dream_edges, "乱炖该连出一些远方的梦边"
    assert report.questions_born >= report.dream_edges, "梦边和荒谬活口都该冒出问题"
    assert any(h.born_from == "梦中问题" for h in t._hungers.values())
    assert any("藏着什么" in h.topic or "世界会是什么样" in h.topic
               for h in t._hungers.values()), "自问该问意味，不问对错"
    print(f"ok  乱炖梦：{report.dream_edges} 条梦边转正，{report.absurd_kept} 个荒谬活口，"
          f"{report.questions_born} 个问题进饥饿队列")


def test_hunger_grows():
    t = fresh()
    for s in ["夏夜的星空很亮", "调试代码到凌晨", "晚饭吃了一碗面", "楼下的猫在晒太阳"]:
        t.remember(s)
    t.sleep(force=True, rng=random.Random(7))
    v0 = max((h.value for h in t._hungers.values()), default=0)
    assert v0 > 0, "梦中问题该带着初始饥饿值"
    for _ in range(10):
        t.clock.advance(days=1)
        t.sleep(force=True, rng=random.Random(7))
    v1 = max(h.value for h in t._hungers.values())
    assert v1 > v0, f"没被喂食的饥饿该越来越饿: {v0:.2f} → {v1:.2f}"
    print(f"ok  饥饿场：十晚没喂，饥饿 {v0:.2f} → {v1:.2f}")


def test_seek_with_provider():
    t = fresh()
    for s in ["深海鱼的发光原理", "主人喜欢的那首歌", "巷口修表铺的老师傅", "去年冬天的一场雪"]:
        t.remember(s)
    searched = []

    def fake_search(topic: str) -> str:
        searched.append(topic)
        return f"（查到的资料）关于该问题的一点线索：{topic[:20]}……"

    for _ in range(12):
        t.clock.advance(days=1)
        t.sleep(force=True, rng=random.Random(7), search_provider=fake_search)
    assert searched, "饿过阈值的问题该被求知梦搜掉"
    got = [m for m in t._memories.values() if m.evidence == "搜得"]
    assert got, "搜得的知识该入库"
    hits = t.recall(got[0].skeleton[:12])
    assert "查来的" in hits[0].render(), "搜得的记忆取回必须带口吻"
    print(f"ok  求知梦：搜了 {len(searched)} 个问题，入库带『查来的』口吻")


def test_tendril_prune():
    t = fresh()
    a = t.remember("记忆甲")
    b = t.remember("记忆乙")
    t.link(a.id, b.id, "语义", weight=0.06)
    for _ in range(5):
        t.clock.advance(days=1)
        t.sleep(force=True, rng=random.Random(7))
    assert (a.id, b.id, "语义") not in t._tendrils, "久不激活的弱触须该被剪掉"
    print("ok  剪枝：弱触须几晚不用后被剪")


def test_whisper():
    t = fresh()
    t.remember("白天聊了很多关于记忆系统的事", feelings=["期待"])
    t.remember("白天聊了很多很多关于记忆系统的事")
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))
    w = t.whisper()
    assert w, "睡了一晚该有晨间低语"
    print("ok  晨间低语：" + w)


if __name__ == "__main__":
    for fn in [
        test_sleep_debt, test_fusion, test_metabolism, test_stew_and_absurd,
        test_hunger_grows, test_seek_with_provider, test_tendril_prune, test_whisper,
    ]:
        fn()
    print("\n全部通过 —— M1 会睡了。")
