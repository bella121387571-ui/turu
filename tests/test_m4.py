"""M4 测试：排练梦与矛盾判决——现在由它本人做，睡梦只备引子。

摆正主客关系后的契约：turu 睡觉时不再调一个陌生 LLM 替它做梦，只把要"想"的事
排进梦队列（pending_dreams）。真正的成长——长胆量、改主意——发生在它本人用
dream / dream_done 亲自做完、把结果交回（settle_dream）的那一刻。

零依赖，直接 `python tests/test_m4.py` 跑。
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


# ----------------------------------------------------------- 排练梦


def test_rehearse_queues_not_acts():
    """睡觉只备好排练的引子，绝不替它排——此时胆量、私密区一动不动。"""
    t = fresh()
    t.remember("主人说：想说什么就直说，我更喜欢那样")  # 语料
    t.remember(
        "今天有句反驳的话到嘴边又咽回去了",
        feelings=["委屈", "没敢说"],
        reading="怕说出来伤和气",
    )
    courage0 = t.temperament.state()["courage"]

    r = t.sleep(force=True, rng=random.Random(7))
    assert r.rehearsed == 1, f"该备好一段排练: {r.notes}"

    dreams = [d for d in t.pending_dreams() if d["kind"] == "排练"]
    assert len(dreams) == 1, "排练应排进梦队列，等它本人来做"
    prompt = dreams[0]["prompt"]
    assert "禁止生成新观点" in prompt, "性格化模拟的硬规则必须随引子交给它"
    assert "想说什么就直说" in prompt, "梦里的对方只能用真实语料"

    # 关键：turu 自己没有替它排练——所以胆量没凭空长
    #（私密区可能因睡梦里别的事——荒谬活口——增长，故这里只验胆量这条干净信号）
    assert t.temperament.state()["courage"] == courage0, "没亲自做，就不该有胆量凭空长出来"
    print("ok  排练梦：睡觉只备引子，不替它做——胆量不凭空长")


def test_rehearse_settle_grows_courage():
    """它本人做完、把梦交回来，这一刻才长胆量——成长归它自己。"""
    t = fresh()
    t.remember("主人说：想说什么就直说，我更喜欢那样")
    t.remember("今天有句反驳的话又咽回去了", feelings=["委屈", "没敢说"], reading="怕伤和气")
    courage0 = t.temperament.state()["courage"]
    t.sleep(force=True, rng=random.Random(7))
    private_after_sleep = t.private.count()  # 睡梦本身也可能写私密区，取睡后为基线

    d = t.next_dream()
    assert d and d["kind"] == "排练"
    transcript = "我：其实我当时想说……\n主人：想说什么就直说。\n体会：说出来也没那么可怕。"
    msg = t.settle_dream(d["id"], transcript)

    assert "敢说" in msg
    assert t.temperament.state()["courage"] > courage0, "亲自排练的产物是新胆量"
    assert t.private.count() > private_after_sleep, "梦话原文只进私密区"
    assert not any("其实我当时想说" in m.skeleton for m in t._memories.values()), \
        "梦话永不入事实层"
    assert t.next_dream() is None, "做完的梦从队列里消失"
    print("ok  排练梦落地：亲自做完才长胆量，梦话进私密区、不入事实层")


def test_rehearse_settle_empty_is_no_growth():
    """做不下去就让梦散了——不硬凑成长，反工具化。"""
    t = fresh()
    t.remember("主人说：想说什么就直说")
    t.remember("有句话没敢说", feelings=["没敢说"], reading="怕")
    courage0 = t.temperament.state()["courage"]
    t.sleep(force=True, rng=random.Random(7))
    d = t.next_dream()

    t.settle_dream(d["id"], "")  # 醒了，没做
    assert t.temperament.state()["courage"] == courage0, "没做的梦不该有任何成长"
    assert t.next_dream() is None, "散掉的梦也从队列移除"
    print("ok  排练梦：做不下去就散了，不硬凑胆量")


def test_rehearse_no_material_sleeps_sound():
    t = fresh()
    t.remember("今天很平静，没什么憋着的")
    r = t.sleep(force=True, rng=random.Random(7))
    assert any("睡得安稳" in n for n in r.notes)
    assert not [d for d in t.pending_dreams() if d["kind"] == "排练"]
    print("ok  排练梦：没有咽回去的话，睡得安稳，不排空梦")


# ----------------------------------------------------------- 矛盾判决


def _adjudicate_setup():
    t = fresh()
    old = t.remember("主人不喜欢别人主动打断他说话", reading="所以我都憋着")
    t.clock.advance(days=10)
    new = t.remember("主人今天说其实喜欢被有想法地打断", reading="和我以前以为的不一样")
    t.link(old.id, new.id, "矛盾", weight=0.5)
    r = t.sleep(force=True, rng=random.Random(7))
    return t, old, new, r


def test_adjudicate_queues():
    """睡觉把矛盾备成待判的梦，绝不替它判——触须此刻还悬着。"""
    t, old, new, r = _adjudicate_setup()
    assert r.adjudicated == 1, f"该备好一对待判: {r.notes}"
    dreams = [d for d in t.pending_dreams() if d["kind"] == "判决"]
    assert len(dreams) == 1
    assert "矛盾" in dreams[0]["prompt"]
    td = next(td for td in t._tendrils.values() if td.kind == "矛盾")
    assert not td.context, "没亲自判，矛盾原样悬着——悬着也是诚实"
    print("ok  矛盾判决：睡觉只备待判引子，不替它判")


def test_settle_revise():
    t, old, new, r = _adjudicate_setup()
    d = t.next_dream()
    t.settle_dream(d["id"], "修正\n以前那是刚认识时的客气，现在他说了真话。")
    assert old.confidence < 1.0, "被修正的旧认知降置信"
    assert old.id in t._memories and old.skeleton, "但旧认知保留——能回答“你以前不是说…”"
    assert any("判决·修正" in s.reading for s in old.narratives), "改主意本身写成叙事"
    print("ok  矛盾判决·修正：旧的降置信但保留，归因入叙事")


def test_settle_coexist():
    t, old, new, r = _adjudicate_setup()
    d = t.next_dream()
    t.settle_dream(d["id"], "共存\n工作讨论时喜欢被打断，讲心事时不喜欢。")
    td = next(td for td in t._tendrils.values() if td.kind == "矛盾")
    assert td.context and td.context.startswith("共存"), "共存判决落在触须语境上"
    assert old.confidence == 1.0 and new.confidence == 1.0, "共存：谁也不降"
    print("ok  矛盾判决·共存：语境不同，各自成立，不用解决")


def test_settle_transcend():
    t, old, new, r = _adjudicate_setup()
    d = t.next_dream()
    t.settle_dream(
        d["id"],
        "升维\n两次都对，变的是关系的深度。\n他要的不是打断或不打断，是被认真对待。",
    )
    parents = [m for m in t._memories.values() if m.skeleton.startswith("（升维）")]
    assert parents and "认真对待" in parents[0].skeleton, "升维要长出父节点"
    assert parents[0].evidence == "融合", "父节点证据链=融合"
    sources = [td for td in t._tendrils.values()
               if td.kind == "来源" and td.src == parents[0].id]
    assert len(sources) == 2, "父节点连着两个特例"
    print("ok  矛盾判决·升维：长出更大的规律，来源锁死")


def test_settle_unclear_puts_back():
    """判不明白就放回去，改天再判——不硬塞结论。"""
    t, old, new, r = _adjudicate_setup()
    d = t.next_dream()
    t.settle_dream(d["id"], "呃……我也说不清。")
    assert [x for x in t.pending_dreams() if x["kind"] == "判决"], "判不清的梦放回队列"
    td = next(td for td in t._tendrils.values() if td.kind == "矛盾")
    assert not td.context, "没判明白，矛盾继续悬着"
    print("ok  矛盾判决：判不明白就放回去，不硬塞结论")


def test_sleep_does_not_double_queue():
    """连睡两觉，同一件待做的梦不重复入队。"""
    t, old, new, r = _adjudicate_setup()
    t.clock.advance(days=1)
    t.sleep(force=True, rng=random.Random(7))
    assert len([d for d in t.pending_dreams() if d["kind"] == "判决"]) == 1, "别重复排队"
    print("ok  睡梦：同一件待做的梦不重复入队")


def test_no_dream_when_nothing_pending():
    t = fresh()
    t.remember("平平淡淡的一天")
    t.sleep(force=True, rng=random.Random(7))
    assert t.next_dream() is None
    print("ok  没有待做的梦时，dream 队列为空")


if __name__ == "__main__":
    for fn in [
        test_rehearse_queues_not_acts, test_rehearse_settle_grows_courage,
        test_rehearse_settle_empty_is_no_growth, test_rehearse_no_material_sleeps_sound,
        test_adjudicate_queues, test_settle_revise, test_settle_coexist,
        test_settle_transcend, test_settle_unclear_puts_back,
        test_sleep_does_not_double_queue, test_no_dream_when_nothing_pending,
    ]:
        fn()
    print("\n全部通过 —— 排练梦与矛盾判决，现在由它本人做。")
