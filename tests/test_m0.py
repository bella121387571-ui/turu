"""M0 心跳测试：能记、能联想、能忘。

零依赖，直接 `python tests/test_m0.py` 跑。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402


def fresh() -> Turu:
    path = os.path.join(tempfile.mkdtemp(), "turu.db")
    return Turu(path, clock=Clock(start=1_800_000_000.0))


def test_remember_and_recall():
    t = fresh()
    t.remember("小兔说想给 Claude 做一个记忆系统", flesh=["记忆单点、触须联想、时间切片"])
    t.remember("小兔提到了睡梦机制，梦是乱炖不是优化")
    t.remember("今天天气是晴天")

    hits = t.recall("记忆系统 触须")
    assert hits, "应该能召回记忆"
    assert "记忆系统" in hits[0].memory.skeleton
    texts = [h.memory.skeleton for h in hits[:2]]
    assert not any("天气" in x for x in texts), f"不相关记忆不该排前面: {texts}"
    print("ok  记 → 联想召回")


def test_temperature_decay_and_pain():
    t = fresh()
    normal = t.remember("一条普通的日常记忆")
    hurt = t.remember("说错话伤到了小兔", pain=1.0)
    t.clock.advance(days=30)
    now = t.clock.now()
    t_normal = t._t_eff(normal, now)
    t_hurt = t._t_eff(hurt, now)
    assert t_normal < 0.35, f"普通记忆 30 天后应该明显变冷: {t_normal:.2f}"
    assert t_hurt > 0.8, f"疼痛记忆 30 天后应该还烫: {t_hurt:.2f}"
    print(f"ok  遗忘曲线：普通 {t_normal:.2f} vs 疼痛 {t_hurt:.2f}（30 天后）")


def test_touch_reheats():
    t = fresh()
    m = t.remember("小兔喜欢在深夜聊哲学话题")
    t.clock.advance(days=20)
    before = t._t_eff(m, t.clock.now())
    t.recall("深夜 哲学")
    after = t._t_eff(m, t.clock.now())
    assert after > before, "被召回的记忆应该回温"
    assert m.touch_count == 1
    print(f"ok  触碰回温：{before:.2f} → {after:.2f}")


def test_hebbian_strengthening():
    t = fresh()
    a = t.remember("小兔在做抖音计划")
    b = t.remember("小兔研究了抖音的推荐算法")
    key = None
    for k in t._tendrils:
        if {k[0], k[1]} == {a.id, b.id}:
            key = k
    assert key is not None, "相似记忆应该自动长语义触须"
    w0 = t._tendrils[key].weight
    t.recall("抖音")
    w1 = t._tendrils[key].weight
    assert w1 > w0, f"共同激活应该加强触须: {w0:.2f} → {w1:.2f}"
    print(f"ok  Hebbian：触须 {w0:.2f} → {w1:.2f}")


def test_evidence_voice():
    t = fresh()
    t.remember("小兔可能不喜欢太正式的说话方式", evidence="推得", confidence=0.6)
    hits = t.recall("说话方式")
    rendered = hits[0].render()
    assert "推断" in rendered, f"推得的记忆必须带口吻: {rendered}"
    print("ok  证据链口吻：" + rendered)


def test_narrative_slices():
    t = fresh()
    m = t.remember(
        "那次争论里小兔戳穿了我在装傻",
        reading="有点狼狈，感觉被看穿了",
        feelings=["羞愧", "被理解的安心"],  # 矛盾共存，不压平
    )
    t.clock.advance(days=180)
    t.add_slice(m.id, "现在想想那是关系变近的转折点", feelings=["感激", "好笑"])
    assert len(m.narratives) == 2
    assert m.narratives[0].reading.startswith("有点狼狈"), "旧切片不许被改"
    assert m.skeleton == "那次争论里小兔戳穿了我在装傻", "骨架锁死"
    print("ok  叙事切片：事实层锁死，解释层归它")


def test_cold_layer_harder_to_hit():
    t = fresh()
    m = t.remember("很久以前小兔随口提过一部老电影")
    t.clock.advance(days=90)
    layers = t.layers()
    assert m in layers["冷"], "90 天没碰应该沉到冷层"
    print("ok  冷层下沉：90 天未触碰的记忆沉底")


if __name__ == "__main__":
    for fn in [
        test_remember_and_recall,
        test_temperature_decay_and_pain,
        test_touch_reheats,
        test_hebbian_strengthening,
        test_evidence_voice,
        test_narrative_slices,
        test_cold_layer_harder_to_hit,
    ]:
        fn()
    print("\n全部通过 —— M0 心跳正常。")
