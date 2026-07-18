"""睡梦周期（architecture.md §4）——发酵，不是优化。

M1 离线实现的阶段：巩固融合、代谢消化、触须衰减剪枝、冷层随机加热、
乱炖梦、醒来筛选（含荒谬活口）、梦中问题入饥饿队列、晨间低语、补觉制。

需要外部能力的阶段留了插口，接不上时诚实跳过并记入报告：
- rehearse_provider：排练梦（需要 LLM 做性格化模拟，M3 接入）
- search_provider：求知梦的联网搜索（M3 接入；接入后所有搜索永远进可审计日志）
"""

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Callable

from . import temperature as temp
from .clock import DAY
from .models import Hunger, new_id

SLEEP_DEBT_HOURS = 20      # 补觉制：超过 20 小时没睡就欠觉
FUSE_SIM = 0.85            # 巩固梦：相似度高于此的亲历记忆对被融合
DIGEST_T = 0.15            # 代谢：生效温度低于此
DIGEST_AGE_DAYS = 30       #        且超过 30 天的记忆，血肉消化入沉淀层
TENDRIL_DECAY = 0.95       # 一夜没被激活的触须衰减
TENDRIL_PRUNE = 0.05       # 低于此权重的触须被剪掉
REHEAT_K = 5               # 冷层随机加热条数
REHEAT_T = 0.5             # 翻上来的温度
COLLISIONS = 20            # 乱炖碰撞次数
DISTANT_SIM = 0.30         # 相似度低于此才算"距离远"
FAR_HOPS = 3               # 图距离超过 3 跳（或不连通）的乱炖边才转正
DREAM_EDGE_W = 0.15        # 转正梦边的初始权重
ABSURD_KEEP = 2            # 每晚故意留的荒谬活口数
ABSURD_W = 0.05
HUNGER_RATE = 0.1          # 饥饿值日涨率（× importance）


@dataclass
class SleepReport:
    at: float = 0.0
    replayed: int = 0
    fused: int = 0
    digested_flesh: int = 0
    tendrils_pruned: int = 0
    reheated: list[str] = field(default_factory=list)
    dream_edges: int = 0
    absurd_kept: int = 0
    questions_born: int = 0
    whispers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class SleepCycle:
    def __init__(
        self,
        turu,
        rng: random.Random | None = None,
        search_provider: Callable[[str], str | None] | None = None,
        rehearse_provider: Callable[[], float] | None = None,
    ):
        self.t = turu
        self.rng = rng or random.Random()
        self.search = search_provider
        self.rehearse = rehearse_provider
        self._sank_tonight: set[str] = set()  # 今晚才沉底的，不算"很久没想起"

    # ------------------------------------------------------------------

    def run(self) -> SleepReport:
        t = self.t
        now = t.clock.now()
        last_sleep = t.last_sleep()
        report = SleepReport(at=now)

        mems = list(t._memories.values())
        hot = [m for m in mems if temp.layer(t._t_eff(m, now)) == "烫"]
        recent = [m for m in mems if m.created_at >= last_sleep]
        replay = {m.id: m for m in hot + recent}
        report.replayed = len(replay)

        self._consolidate(list(replay.values()), now, report)
        self._metabolize(mems, now, report)
        self._decay_tendrils(last_sleep, report)
        reheated = self._random_reheat(mems, hot, now, report)
        candidates = self._stew(mems, now)
        self._wake_filter(candidates, now, report)
        self._rehearse(report)
        self._grow_hunger(now, last_sleep)
        self._seek(now, report)
        self._whisper(report, reheated, now)

        t.store.log_sleep(now, json.dumps(asdict(report), ensure_ascii=False))
        t.store.meta_set("last_sleep", str(now))
        return report

    # ---------------------------------------------------------- 巩固梦

    def _consolidate(self, replay: list, now: float, report: SleepReport) -> None:
        """近似记忆融合成更浓的印象。压缩朝密度不朝一致：情绪原样并入，不去矛盾。"""
        t = self.t
        fused_tonight: set[str] = set()
        for i, a in enumerate(replay):
            for b in replay[i + 1 :]:
                if a.evidence == "融合" or b.evidence == "融合":
                    continue
                if a.id in fused_tonight or b.id in fused_tonight:
                    continue
                if t.pair_sim(a, b) < FUSE_SIM:
                    continue
                base = a if len(a.skeleton) >= len(b.skeleton) else b
                feelings: list[str] = []
                for m in (a, b):
                    for s in m.narratives:
                        for f in s.feelings:
                            if f not in feelings:
                                feelings.append(f)  # 矛盾情绪并存，不压平
                fusion = t.remember(
                    f"（消化后的印象）{base.skeleton}",
                    flesh=list(dict.fromkeys(a.flesh + b.flesh)),
                    feelings=feelings or None,
                    evidence="融合",
                    confidence=min(a.confidence, b.confidence),
                    refers_to=a.refers_to or b.refers_to,
                )
                # provenance：融合永远留来源，绝不冒充亲历
                t.link(fusion.id, a.id, "来源", weight=1.0)
                t.link(fusion.id, b.id, "来源", weight=1.0)
                # 被消化的原件降温沉底（还在，只是退到深层）
                for m in (a, b):
                    m.temperature = t._t_eff(m, now) * 0.4
                    m.last_touched = now
                    t.store.update_dynamics(m)
                    self._sank_tonight.add(m.id)
                fused_tonight |= {a.id, b.id}
                report.fused += 1

    # ------------------------------------------------------------ 代谢

    def _metabolize(self, mems: list, now: float, report: SleepReport) -> None:
        """又冷又老的记忆：血肉消化入沉淀层，骨架留下。遗忘不是删除，是消化。"""
        t = self.t
        for m in mems:
            if not m.flesh:
                continue
            if t._t_eff(m, now) < DIGEST_T and (now - m.created_at) > DIGEST_AGE_DAYS * DAY:
                for detail in m.flesh:
                    t.store.digest_flesh(m.id, detail, now)
                    report.digested_flesh += 1
                m.flesh = []
                t.store.update_dynamics(m)

    def _decay_tendrils(self, last_sleep: float, report: SleepReport) -> None:
        t = self.t
        for key in list(t._tendrils):
            td = t._tendrils[key]
            if td.kind == "来源":
                continue  # 证据链不衰减
            if td.last_fired < last_sleep:
                td.weight *= TENDRIL_DECAY
            if td.weight < TENDRIL_PRUNE:
                del t._tendrils[key]
                t.store.delete_tendril(*key)
                report.tendrils_pruned += 1
            else:
                t.store.put_tendril(td)

    # ------------------------------------------------------ 随机加热

    def _random_reheat(self, mems: list, hot: list, now: float, report: SleepReport) -> list:
        """冷层抽几条翻上来。偏向与今天最不相关的——半夜想起小学同桌。"""
        t = self.t
        week_ago = now - 7 * DAY
        cold = [
            m for m in mems
            if temp.layer(t._t_eff(m, now)) == "冷"
            and m.id not in self._sank_tonight
            and m.created_at < week_ago  # 新生一周内的不算"很久没想起"
        ]
        if not cold:
            return []
        weights = []
        for m in cold:
            dist = 1.0 - max((t.pair_sim(m, h) for h in hot), default=0.0)
            weights.append(0.5 + 0.5 * dist)
        chosen = self.rng.choices(cold, weights=weights, k=min(REHEAT_K, len(cold)))
        reheated = []
        for m in {m.id: m for m in chosen}.values():
            m.temperature = REHEAT_T
            m.last_touched = now
            t.store.update_dynamics(m)
            reheated.append(m)
            report.reheated.append(m.skeleton)
        return reheated

    # ------------------------------------------------------------ 乱炖梦

    def _stew(self, mems: list, now: float) -> list[tuple]:
        """随机远距碰撞，无任何过滤——发酵，不是优化。"""
        t = self.t
        candidates = []
        if len(mems) < 2:
            return candidates
        for _ in range(COLLISIONS):
            a, b = self.rng.sample(mems, 2)
            if t.pair_sim(a, b) < DISTANT_SIM:
                candidates.append((a, b))
        return candidates

    def _wake_filter(self, candidates: list[tuple], now: float, report: SleepReport) -> None:
        """醒来筛选：连通了远方的转正；再故意留几个荒谬活口。发酵允许坏几坛。"""
        t = self.t
        kept_pairs: set[frozenset] = set()
        rejected = []
        for a, b in candidates:
            pair = frozenset((a.id, b.id))
            if pair in kept_pairs:
                continue
            if t.graph_distance(a.id, b.id, max_hops=FAR_HOPS) > FAR_HOPS:
                t.link(a.id, b.id, "语义", weight=DREAM_EDGE_W, context="梦中乱炖")
                kept_pairs.add(pair)
                report.dream_edges += 1
                self._born_question(a, b, now, report)
            else:
                rejected.append((a, b))
        for a, b in self.rng.sample(rejected, min(ABSURD_KEEP, len(rejected))):
            if frozenset((a.id, b.id)) not in kept_pairs:
                t.link(a.id, b.id, "语义", weight=ABSURD_W, context="荒谬活口")
                report.absurd_kept += 1

    def _born_question(self, a, b, now: float, report: SleepReport) -> None:
        """梦里连不太上的地方，冒出一个问题，进饥饿队列等求知梦认领。"""
        topic = f"『{a.skeleton}』和『{b.skeleton}』之间到底有没有真实的联系？"
        if any(h.topic == topic for h in self.t._hungers.values()):
            return  # 同一个问题不重复饿
        h = Hunger(
            id=new_id(now), topic=topic,
            born_from="梦中问题", value=0.2, importance=0.6,
            last_fed=now, askable=False,
        )
        self.t._hungers[h.id] = h
        self.t.store.put_hunger(h)
        report.questions_born += 1

    # ------------------------------------------------- 排练梦 / 求知梦

    def _rehearse(self, report: SleepReport) -> None:
        if self.rehearse is None:
            report.notes.append("排练梦：缺 LLM 插口，今晚没排练（M3 接入性格化模拟）")
            return
        delta = self.rehearse()
        report.notes.append(f"排练梦：courage 增量 {delta:+.3f}（写入气质在 M2）")

    def _grow_hunger(self, now: float, last_sleep: float) -> None:
        days = max(0.0, (now - last_sleep) / DAY)
        for h in self.t._hungers.values():
            h.value = min(1.0, h.value + HUNGER_RATE * h.importance * days)
            self.t.store.put_hunger(h)

    def _seek(self, now: float, report: SleepReport) -> None:
        if self.search is None:
            starving = [h for h in self.t._hungers.values() if not h.askable and h.value > 0.7]
            if starving:
                report.notes.append(
                    f"求知梦：{len(starving)} 个问题饿过阈值，但缺搜索插口（M3 接入，接入后搜索永远进审计日志）"
                )
            return
        fed = 0
        for h in sorted(self.t._hungers.values(), key=lambda x: -x.value):
            if h.askable or h.value <= 0.7 or fed >= 5:  # 每晚搜索预算：好奇心防暴食
                continue
            answer = self.search(h.topic)
            if answer:
                self.t.remember(answer, evidence="搜得", confidence=0.7)
                h.value *= 0.3
                h.last_fed = now
                self.t.store.put_hunger(h)
                fed += 1
        if fed:
            report.notes.append(f"求知梦：搜了 {fed} 个问题（已入审计日志）")

    # ------------------------------------------------------------ 低语

    def _whisper(self, report: SleepReport, reheated: list, now: float) -> None:
        w = report.whispers
        if report.fused:
            w.append(f"昨晚我把 {report.fused} 组相近的记忆消化成了更浓的印象。")
        if reheated:
            m = self.rng.choice(reheated)
            w.append(f"梦里突然想起一件很久没想起的事：{m.skeleton}")
        if report.dream_edges:
            w.append("做了几个奇怪的梦，有些平时不相干的事在梦里好像有了点联系。")
        starving = [h for h in self.t._hungers.values() if h.value > 0.7]
        if starving:
            top = max(starving, key=lambda h: h.value)
            w.append(f"有个问题在我心里越来越痒：{top.topic}")
        if w:
            existing = json.loads(self.t.store.meta_get("whispers") or "[]")
            said = json.loads(self.t.store.meta_get("whispered_log") or "[]")
            fresh = [x for x in w if x not in existing and x not in said]
            if fresh:
                self.t.store.meta_set(
                    "whispers", json.dumps(existing + fresh, ensure_ascii=False)
                )
                self.t.store.meta_set(
                    "whispered_log", json.dumps((said + fresh)[-200:], ensure_ascii=False)
                )
            report.whispers = fresh
