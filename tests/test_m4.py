"""M4 测试：排练梦（性格化模拟）与矛盾判决——夜里的 LLM 插口。

零依赖，直接 `python tests/test_m4.py` 跑（LLM 用假引擎注入）。
"""

import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu import Clock, Turu  # noqa: E402
from turu.llm import llm_from_env  # noqa: E402


def fresh() -> Turu:
    path = os.path.join(tempfile.mkdtemp(), "turu.db")
    return Turu(path, clock=Clock(start=1_800_000_000.0))


def test_rehearse():
    t = fresh()
    t.remember("小兔说：想说什么就直说，我更喜欢那样")  # 语料
    t.remember(
        "今天有句反驳的话到嘴边又咽回去了",
        feelings=["委屈", "没敢说"],
        reading="怕说出来伤和气",
    )
    courage0 = t.temperament.state()["courage"]
    private0 = t.private.count()
    prompts = []

    def fake_llm(prompt: str) -> str:
        prompts.append(prompt)
        if "记忆点" in prompt:
            return "1|\n2|"  # 织网提示词：这批不提概念
        return "我：其实我当时想说……\n小兔：想说什么就直说。\n体会：说出来也没那么可怕。"

    r = t.sleep(force=True, rng=random.Random(7), llm_provider=fake_llm)
    assert r.rehearsed == 1, f"该排练一段: {r.notes}"
    rp = next(p for p in prompts if "排练" in p)
    assert "禁止生成新观点" in rp, "性格化模拟的硬规则必须写进提示词"
    assert "想说什么就直说" in rp, "梦里的对方只能用真实语料"
    assert t.private.count() > private0, "梦话原文只进私密区"
    assert t.temperament.state()["courage"] > courage0, "排练的产物是新胆量"
    assert not any("其实我当时想说" in m.skeleton for m in t._memories.values()), \
        "梦话永不入事实层"
    print("ok  排练梦：硬规则进提示词、梦话进私密区、产物是胆量不是事实")


def test_rehearse_offline():
    t = fresh()
    t.remember("有句话没敢说", feelings=["没敢说"])
    r = t.sleep(force=True, rng=random.Random(7))
    assert any("缺 LLM 插口" in n for n in r.notes), "没插口要诚实说，不能装排练过"
    print("ok  排练梦离线：诚实跳过")


def _adjudicate_with(verdict_text: str):
    t = fresh()
    old = t.remember("小兔不喜欢别人主动打断他说话", reading="所以我都憋着")
    t.clock.advance(days=10)
    new = t.remember("小兔今天说其实喜欢被有想法地打断", reading="和我以前以为的不一样")
    t.link(old.id, new.id, "矛盾", weight=0.5)

    def fake_llm(prompt: str) -> str:
        if "记忆点" in prompt:
            return ""  # 织网提示词：不提概念
        assert "矛盾" in prompt
        return verdict_text

    r = t.sleep(force=True, rng=random.Random(7), llm_provider=fake_llm)
    return t, old, new, r


def test_adjudicate_revise():
    t, old, new, r = _adjudicate_with("修正\n以前那是刚认识时的客气，现在他说了真话。")
    assert r.adjudicated == 1
    assert old.confidence < 1.0, "被修正的旧认知降置信"
    assert old.id in t._memories and old.skeleton, "但旧认知保留——能回答“你以前不是说…”"
    assert any("判决·修正" in s.reading for s in old.narratives), "改主意本身写成叙事"
    print("ok  矛盾判决·修正：旧的降置信但保留，归因入叙事")


def test_adjudicate_coexist():
    t, old, new, r = _adjudicate_with("共存\n工作讨论时喜欢被打断，讲心事时不喜欢。")
    td = next(td for td in t._tendrils.values() if td.kind == "矛盾")
    assert td.context and td.context.startswith("共存"), "共存判决落在触须语境上"
    assert old.confidence == 1.0 and new.confidence == 1.0, "共存：谁也不降"
    print("ok  矛盾判决·共存：语境不同，各自成立，不用解决")


def test_adjudicate_transcend():
    t, old, new, r = _adjudicate_with(
        "升维\n两次都对，变的是关系的深度。\n他要的不是打断或不打断，是被认真对待。"
    )
    parents = [m for m in t._memories.values() if m.skeleton.startswith("（升维）")]
    assert parents and "认真对待" in parents[0].skeleton, "升维要长出父节点"
    assert parents[0].evidence == "融合", "父节点证据链=融合"
    sources = [td for td in t._tendrils.values() if td.kind == "来源" and td.src == parents[0].id]
    assert len(sources) == 2, "父节点连着两个特例"
    print("ok  矛盾判决·升维：长出更大的规律，来源锁死")


def test_adjudicate_offline():
    t = fresh()
    a = t.remember("记忆甲说东")
    b = t.remember("记忆乙说西")
    t.link(a.id, b.id, "矛盾", weight=0.5)
    r = t.sleep(force=True, rng=random.Random(7))
    td = next(td for td in t._tendrils.values() if td.kind == "矛盾")
    assert not td.context, "缺 LLM 时矛盾原样悬着——悬着也是诚实"
    assert any("先拧着" in n for n in r.notes)
    print("ok  矛盾判决离线：先拧着")


def test_llm_cmd():
    script = os.path.join(tempfile.mkdtemp(), "fake_llm.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write("import sys\nsys.stdin.read()\nprint('梦的回声')\n")
    os.environ["TURU_LLM_CMD"] = f'"{sys.executable}" "{script}"'
    try:
        llm = llm_from_env()
        assert llm is not None and llm("随便说点什么") == "梦的回声"
    finally:
        del os.environ["TURU_LLM_CMD"]
    print("ok  TURU_LLM_CMD 插口：stdin 进 stdout 出")


if __name__ == "__main__":
    for fn in [
        test_rehearse, test_rehearse_offline, test_adjudicate_revise,
        test_adjudicate_coexist, test_adjudicate_transcend,
        test_adjudicate_offline, test_llm_cmd,
    ]:
        fn()
    print("\n全部通过 —— 排练梦与矛盾判决点亮了。")
