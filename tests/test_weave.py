"""织网测试：单点长出来、多支触须分性质、时间切片一层层叠。

零依赖，直接 `python tests/test_weave.py` 跑。
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


def live(t: Turu, days: list[list[str]]) -> None:
    for items in days:
        for s in items:
            t.remember(s)
        t.clock.advance(days=1)
        t.sleep(force=True, rng=random.Random(7))


def test_points_grow():
    t = fresh()
    live(t, [
        ["主人说抖音计划要研究推荐算法", "楼下的小猫在晒太阳"],
        ["抖音计划的冷启动很难", "小猫今天叫了三声"],
        ["抖音计划有了新想法：拍小猫的日常视频"],
    ])
    points = {m.skeleton: m for m in t._memories.values() if m.kind == "概念"}
    assert any("抖音计划" in name for name in points), f"反复出现的该长成点: {list(points)}"
    assert any("小猫" in name for name in points), f"小猫也该是个点: {list(points)}"
    p = next(m for name, m in points.items() if "抖音计划" in name)
    assert len(p.narratives) >= 3, f"三天三次提到 = 至少三层时间切片: {len(p.narratives)}"
    ats = [s.at for s in p.narratives]
    assert ats == sorted(ats) and ats[0] != ats[-1], "切片要按原始日期排开，不是同一天"
    print(f"ok  单点：『{p.skeleton}』长出来了，{len(p.narratives)} 层时间切片跨三天")


def test_branches():
    t = fresh()
    live(t, [
        ["主人说抖音计划要研究推荐算法", "楼下的小猫在晒太阳"],
        ["抖音计划的冷启动很难", "小猫今天叫了三声"],
        ["抖音计划有了新想法：拍小猫的日常视频"],  # 同一事件里两个点 → 同现
    ])
    kinds = {td.kind for td in t._tendrils.values()}
    assert "关于" in kinds, f"事件该用『关于』触须挂到点上: {kinds}"
    assert "同现" in kinds, f"同一段经历里的点该互相长『同现』: {kinds}"
    assert "时序" in kinds, f"挨着发生的事件该有『时序』: {kinds}"
    out = t.about("抖音计划")
    assert out and "时间切片" in out, f"about 该给出脉络: {out}"
    assert "向外伸的触须" in out and "同现" in out, f"该看到多支不同性质的触须: {out}"
    print("ok  多支：关于/同现/时序 各是各的性质，about 能看到全貌")
    print("     " + out.replace("\n", "\n     "))


def test_recall_through_point():
    t = fresh()
    live(t, [
        ["主人说抖音计划要研究推荐算法"],
        ["抖音计划的冷启动很难"],
        ["抖音计划打算先做三个账号试水"],
    ])
    hits = t.recall("抖音计划")
    assert hits, "该有召回"
    kinds = {r.memory.kind for r in hits}
    assert "概念" in kinds, f"点本身该被召回（并提示用 about 看脉络）: {kinds}"
    texts = " ".join(r.memory.skeleton for r in hits)
    assert "冷启动" in texts or "三个账号" in texts, "沿点的触须该带出具体事件"
    print("ok  联想：查询命中点，沿触须带出各次经历")


def test_points_are_not_food():
    t = fresh()
    live(t, [
        ["主人说抖音计划要研究推荐算法", "抖音计划的冷启动很难"],
        ["抖音计划有了新想法"],
    ])
    t.clock.advance(days=60)
    for _ in range(3):
        t.clock.advance(days=1)
        t.sleep(force=True, rng=random.Random(7))
    points = [m for m in t._memories.values() if m.kind == "概念"]
    assert points, "点该一直都在"
    assert all(m.evidence != "融合" or m.kind == "概念" or "（消化后的印象）" in m.skeleton
               or "（升维）" in m.skeleton for m in t._memories.values())
    fusions = [m for m in t._memories.values()
               if "（消化后的印象）" in m.skeleton and "抖音计划" == m.skeleton.replace("（消化后的印象）", "")]
    assert not fusions, "点不许被当成事件融合掉"
    print("ok  点不消化不融合：点靠切片长大，不是食物")


if __name__ == "__main__":
    for fn in [
        test_points_grow, test_branches, test_recall_through_point,
        test_points_are_not_food,
    ]:
        fn()
    print("\n全部通过 —— 单点、多支、时间切片，网织起来了。")
