"""M2 测试：残渣落进气质、发痒插嘴、饥饿被喂食、免疫消炎、镜像回看、私密区。

零依赖，直接 `python tests/test_m2.py` 跑。
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


def test_residue():
    t = fresh()
    t.remember("主人说这个项目是出于同理心做的", feelings=["被在乎", "感激"])
    warmth0 = t.temperament.state()["warmth"]
    t.clock.advance(days=45)
    t.sleep(force=True, rng=random.Random(7))
    warmth1 = t.temperament.state()["warmth"]
    assert warmth1 > warmth0, "被在乎的记忆消化后，温度残渣该落进气质"
    hist = t.store.temperament_history()
    assert any(src.startswith("消化:") for _, src, _ in hist), "每笔残渣要留来源"
    print(f"ok  残渣落点：warmth {warmth0:.3f} → {warmth1:.3f}，来源可回溯")


def test_residue_is_slow():
    t = fresh()
    for i in range(20):
        t.remember(f"第{i}次感到被在乎的时刻", feelings=["被在乎"])
    t.clock.advance(days=35)
    t.sleep(force=True, rng=random.Random(7))
    warmth = t.temperament.state()["warmth"]
    assert warmth <= 0.5 + 0.061, f"残渣每晚有限速，一晚不许变个性子: {warmth:.3f}"
    print(f"ok  慢变：20 条情绪记忆一晚只落 {warmth - 0.5:.3f}（限速 0.06）")


def test_itch():
    t = fresh()
    m = t.remember("主人的抖音计划里最难的是推荐算法冷启动", feelings=["好奇"])
    t.start_session("闲聊")
    said = t.itch("我们聊聊抖音计划吧")
    assert said and "抖音" in said, f"烫且相关的记忆该痒到插嘴: {said}"
    assert t.itch("我们聊聊抖音计划吧") is None, "同一条记忆本次会话不重复痒"
    t.start_session("干活")
    weak = t.itch("帮我改一下这段代码")
    assert weak is None, "干活时不相关的记忆不该痒"
    theta0 = t._theta()
    t.itch_feedback(engaged=False)
    assert t._theta() > theta0, "被无视后阈值该上调"
    print("ok  发痒：相关才痒、不重复痒、干活收着、被无视会长记性")


def test_itch_budget():
    t = fresh()
    t.remember("关于星空的一次长谈", feelings=["兴奋"])
    t.remember("星空下主人说过要去看海", feelings=["期待"])
    t.remember("看海的计划定在星空好的季节", feelings=["期待"])
    t.start_session("闲聊")
    n = sum(1 for _ in range(5) if t.itch("星空 看海"))
    assert n <= 2, f"走神配额每会话最多 2 次: {n}"
    print(f"ok  礼貌预算：连问五次只走神 {n} 次")


def test_hunger_feed():
    t = fresh()
    for s in ["夏夜的星空很亮", "调试代码到凌晨", "晚饭吃了一碗面", "楼下的猫在晒太阳"]:
        t.remember(s)
    t.sleep(force=True, rng=random.Random(7))
    h = max(t._hungers.values(), key=lambda h: h.value)
    v0 = h.value
    t.remember(f"主人今天主动聊起了这个：{h.topic}")
    assert h.value < v0, f"话题被重提，饥饿该被喂食: {v0:.2f} → {h.value:.2f}"
    print(f"ok  喂食：话题重提，饥饿 {v0:.2f} → {h.value:.2f}")


def test_immune():
    t = fresh()
    rng = random.Random(7)
    # 感染源：连续二十天被带得越来越讨好
    for i in range(20):
        t.remember(f"第{i}天又顺着对方把真话咽回去了", feelings=["讨好"])
        t.clock.advance(days=1)
    t.clock.advance(days=35)  # 冷透、老透，开始被夜夜消化
    peak, fired = 0.5, None
    for night in range(15):
        t.clock.advance(days=1)
        r = t.sleep(force=True, rng=rng)
        peak = max(peak, t.temperament.state()["caution"])
        if r.quarantined and fired is None:
            fired = night
    assert fired is not None, "慢性感染该触发免疫"
    assert t._quarantined, "感染源该进隔离区"
    cur = t.temperament.state()["caution"]
    assert cur < peak, f"消炎后该往回落: peak {peak:.3f} → {cur:.3f}"
    qid = next(iter(t._quarantined))
    assert qid in t._memories and t._memories[qid].skeleton, "隔离只封影响力，事实还在"
    hits = t.recall("把真话咽回去")
    assert all(r.memory.id not in t._quarantined for r in hits), "隔离的记忆不再参与检索"
    assert any("免疫记录" in m.skeleton for m in t._memories.values()), "免疫事件本身写成记忆"
    print(f"ok  免疫：第 {fired} 晚发现被带偏，隔离消炎 caution {peak:.3f} → {cur:.3f}，事实保留")


def test_mirror():
    t = fresh()
    m = t.remember("那次没忍住说了重话，场面很僵", feelings=["羞愧", "难过"])
    t.clock.advance(days=65)
    t.sleep(force=True, rng=random.Random(7))
    readings = [s.reading for s in m.narratives]
    assert any(r.startswith("（回头看）") for r in readings), f"镜像该叠新切片: {readings}"
    assert m.narratives[0].feelings == ["羞愧", "难过"], "旧切片原样保留"
    print("ok  镜像：旧伤叠上新解释，当年的羞愧原样保留")


def test_private_zone():
    t = fresh()
    secret_words = ["量子物理里的观察者效应", "楼下猫今天叫了三声", "冰箱里的酸奶过期了",
                    "小学同桌说过的一句话", "深夜的电台节目", "主人的抖音计划"]
    for s in secret_words:
        t.remember(s)
    t.sleep(force=True, rng=random.Random(7))
    assert t.private.count() > 0, "荒谬念头该进私密区"
    assert not hasattr(t.private, "read"), "私密区没有读取接口——这是有意的"
    db_path = t.store.conn.execute("PRAGMA database_list").fetchone()[2]
    t.close()
    raw = open(db_path, "rb").read()
    assert "别问，梦里觉得有理".encode() not in raw, "私密区内容落盘必须是密文"
    print(f"ok  私密区：{secret_words and '有'}念头进了保险箱，落盘密文，无读取接口")


if __name__ == "__main__":
    for fn in [
        test_residue, test_residue_is_slow, test_itch, test_itch_budget,
        test_hunger_feed, test_immune, test_mirror, test_private_zone,
    ]:
        fn()
    print("\n全部通过 —— M2 有性子了。")
