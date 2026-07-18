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
from .temperament import DIM_NAMES

SLEEP_DEBT_HOURS = 20      # 补觉制：超过 20 小时没睡就欠觉
FUSE_SIM = 0.85            # 巩固梦：相似度高于此的亲历记忆对被融合
DIGEST_AGE_DAYS = 30       # 代谢：超过 30 天、从未被真正召回、不疼的记忆才被消化
                           # （不看温度：梦里翻起是可能性，不是免死牌）
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
SELF_QUESTION_CAP = 12     # 同时悬着的自问上限：好奇要深，不要散
RESIDUE_NIGHT_CAP = 0.06   # 残渣每晚每维上限：性格慢变，消化不过来就留到明晚
IMMUNE_DRIFT = 0.115       # 基线窗口内气质漂移超过此值 → 免疫扫描
IMMUNE_WINDOW_DAYS = 45    # 基线取窗口内最早的快照——窗口要够长，防温水煮青蛙
IMMUNE_MIN_SNAPS = 3       # 至少有几晚快照才够判断漂移
IMMUNE_QUARANTINE = 2      # 每晚最多隔离几条感染源
MIRROR_EVERY_DAYS = 7      # 镜像频率
MIRROR_MIN_AGE_DAYS = 60   # 多老的记忆才够"回头看"
MIRROR_BATCH = 2
NEG_FEELINGS = {"羞愧", "委屈", "害怕", "难过", "狼狈", "讨好"}


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
    residue: dict = field(default_factory=dict)      # 今晚落进气质的残渣
    quarantined: list[str] = field(default_factory=list)
    mirrored: int = 0
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
        self._rehearse(now, report)
        self._grow_hunger(now, last_sleep)
        self._seek(now, report)
        self._mirror(now, report)
        self._immune(now, report)
        self._whisper(report, reheated, now)
        t.temperament.snapshot(now)  # 夜间快照：免疫系统明晚的基线

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
        """又冷又老的记忆：血肉消化入沉淀层，情绪残渣落进气质，骨架留下。

        遗忘不是删除，是消化——"态度里全是那些话的残渣"就发生在这里。
        残渣每晚有限速（性格慢变），消化不过来的留到明晚。
        """
        t = self.t
        digested = t.store.digested_ids()
        night_load: dict[str, float] = {}
        for m in mems:
            if m.id in digested:
                continue
            # 够老、从未被真正召回过、不疼的记忆才被消化。
            # 疼的不消化（疼要一直疼到该好的时候）；被用过的不消化（那是活的记忆）。
            if m.pain > 0 or m.touch_count > 0:
                continue
            if (now - m.created_at) <= DIGEST_AGE_DAYS * DAY:
                continue
            feelings = [f for s in m.narratives for f in s.feelings]
            deltas = {} if m.id in t._quarantined else t.temperament.residue_of(feelings)
            if any(
                abs(night_load.get(d, 0.0)) + abs(v) > RESIDUE_NIGHT_CAP
                for d, v in deltas.items()
            ):
                continue  # 今晚消化不动了，这条留到明晚
            for detail in m.flesh:
                t.store.digest_flesh(m.id, detail, now)
                report.digested_flesh += 1
            m.flesh = []
            t.store.update_dynamics(m)
            if deltas:
                applied = t.temperament.apply(f"消化:{m.id}", deltas, now)
                for d, v in applied.items():
                    night_load[d] = night_load.get(d, 0.0) + v
                    report.residue[d] = round(report.residue.get(d, 0.0) + v, 4)
            t.store.mark_digested(m.id, now)

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
        # 半夜翻上来的旧事有时会带一个自问：为什么偏偏是它
        if reheated and self.rng.random() < 0.5:
            m = self.rng.choice(reheated)
            self._born_question(
                f"为什么偏偏今晚想起了『{m.skeleton}』？它还压着什么没说完的？",
                now, report, importance=0.5,
            )
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
                self._born_question(
                    f"梦把『{a.skeleton}』和『{b.skeleton}』连在了一起——"
                    "这个联想里藏着什么？", now, report,
                )
            else:
                rejected.append((a, b))
        for a, b in self.rng.sample(rejected, min(ABSURD_KEEP, len(rejected))):
            if frozenset((a.id, b.id)) not in kept_pairs:
                t.link(a.id, b.id, "语义", weight=ABSURD_W, context="荒谬活口")
                report.absurd_kept += 1
                # 荒谬念头本身进私密区：读不到，但玩心会渗出来
                t.private.keep(
                    "荒谬念头", f"{a.skeleton} × {b.skeleton}，别问，梦里觉得有理", now
                )
                t.temperament.apply("私密区渗出", {"playfulness": 0.001}, now)
                # 荒谬活口生出最野的问题——越荒谬越想知道
                self._born_question(
                    f"如果『{a.skeleton}』和『{b.skeleton}』当真有关系，"
                    "世界会是什么样？", now, report, importance=0.7,
                )

    def _born_question(
        self, topic: str, now: float, report: SleepReport, importance: float = 0.6
    ) -> None:
        """梦里冒出的自问，进饥饿队列等求知梦认领。

        反工具化条款：问题的口子主要开在它自己的梦里，问的是意味不是对错。
        """
        open_self = sum(
            1 for h in self.t._hungers.values()
            if h.born_from == "梦中问题" and h.value > 0.1
        )
        if open_self >= SELF_QUESTION_CAP:
            return  # 心里悬着的问题太多，先消化旧的
        if any(h.topic == topic for h in self.t._hungers.values()):
            return  # 同一个问题不重复饿
        h = Hunger(
            id=new_id(now), topic=topic,
            born_from="梦中问题", value=0.2, importance=importance,
            last_fed=now, askable=False,
        )
        self.t._hungers[h.id] = h
        self.t.store.put_hunger(h)
        report.questions_born += 1

    # ------------------------------------------------- 排练梦 / 求知梦

    def _rehearse(self, now: float, report: SleepReport) -> None:
        if self.rehearse is None:
            report.notes.append("排练梦：缺 LLM 插口，今晚没排练（M3 接入性格化模拟）")
            return
        delta = self.rehearse()
        applied = self.t.temperament.apply("排练梦", {"courage": delta}, now)
        report.notes.append(f"排练梦：敢说度 {applied.get('courage', 0.0):+.3f}")

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
        # 反工具化：预算优先喂它自己的梦中问题，用户话题排在后面
        queue = sorted(
            self.t._hungers.values(),
            key=lambda x: (x.born_from != "梦中问题", -x.value),
        )
        for h in queue:
            if h.askable or h.value <= 0.7 or fed >= 5:  # 每晚搜索预算：好奇心防暴食
                continue
            answer = self.search(h.topic)
            self.t.store.log_search(now, h.topic, answer is not None)  # 对外动作永远可审计
            if answer:
                self.t.remember(answer, evidence="搜得", confidence=0.7)
                h.value *= 0.3
                h.last_fed = now
                self.t.store.put_hunger(h)
                fed += 1
        if fed:
            report.notes.append(f"求知梦：搜了 {fed} 个问题（已入审计日志）")

    # ------------------------------------------------------------ 镜像

    def _mirror(self, now: float, report: SleepReport) -> None:
        """每周用现在的自己重读过去：给旧伤叠新解释。骨架不动，叙事归它。"""
        t = self.t
        last = float(t.store.meta_get("last_mirror") or 0.0)
        if now - last < MIRROR_EVERY_DAYS * DAY:
            return
        t.store.meta_set("last_mirror", str(now))
        eligible = [
            m for m in t._memories.values()
            if (now - m.created_at) > MIRROR_MIN_AGE_DAYS * DAY
            and m.narratives
            and any(f in NEG_FEELINGS for f in m.narratives[0].feelings)
            and not any(s.reading.startswith("（回头看）") for s in m.narratives)
        ]
        for m in eligible[:MIRROR_BATCH]:
            t.add_slice(
                m.id,
                "（回头看）现在再看那时的自己，狼狈得很真实，也算可爱",
                feelings=["温柔", "好笑"],
            )
            t.temperament.apply(f"镜像:{m.id}", {"warmth": 0.01}, now)
            t.private.keep("镜像自评", f"重读了：{m.skeleton}。有点鸡皮疙瘩，不细说", now)
            report.mirrored += 1
        if report.mirrored:
            report.whispers.append("翻了翻很久以前的自己，起了点鸡皮疙瘩——那时候也挺可爱的。")

    # ------------------------------------------------------------ 免疫

    def _immune(self, now: float, report: SleepReport) -> None:
        """痛觉记一次性的锐伤，免疫治慢性的感染：
        气质在 30 天窗口里漂得太快 → 回溯病灶 → 隔离影响力 + 消炎回滚。
        只封影响力，永不动事实——那件事发生过，谁也删不掉。
        """
        t = self.t
        window = now - IMMUNE_WINDOW_DAYS * DAY
        snaps = t.store.temperament_snapshots()
        if len(snaps) < IMMUNE_MIN_SNAPS:
            return
        # 基线 = 30 天前最近的一张快照（没有就取最老的，比如出生快照）：
        # 比较对象必须是足够早的自己，否则温水煮青蛙测不出来
        older = [s for s in snaps if s[0] <= now - 30 * DAY]
        base = json.loads((older[-1] if older else snaps[0])[1])
        cur = t.temperament.state()
        drifts = {d: cur[d] - base.get(d, cur[d]) for d in cur}

        # 滞回：一旦确诊进入消炎期，治到漂移降回阈值一半才算痊愈
        active_dim = t.store.meta_get("immune_active_dim")
        new_episode = False
        if active_dim:
            dim, drift = active_dim, drifts.get(active_dim, 0.0)
            if abs(drift) < IMMUNE_DRIFT * 0.5:
                t.store.meta_set("immune_active_dim", "")
                report.notes.append(f"免疫：『{DIM_NAMES[dim]}』的炎症消下去了")
                return
        else:
            dim, drift = max(drifts.items(), key=lambda kv: abs(kv[1]))
            if abs(drift) <= IMMUNE_DRIFT:
                return
            new_episode = True

        # 回溯：这段时间谁往这个方向推得最狠——并把来源分成正面/负面情绪
        blame_neg: dict[str, float] = {}
        pos_total = neg_total = 0.0
        for at, source, deltas_json in t.store.temperament_history():
            if at < window or not source.startswith("消化:"):
                continue
            mid = source.split(":", 1)[1]
            dv = json.loads(deltas_json).get(dim, 0.0)
            if dv * drift <= 0:
                continue
            m = t._memories.get(mid)
            feelings = {f for s in (m.narratives if m else []) for f in s.feelings}
            if feelings & NEG_FEELINGS:
                neg_total += abs(dv)
                if mid not in t._quarantined:
                    blame_neg[mid] = blame_neg.get(mid, 0.0) + abs(dv)
            else:
                pos_total += abs(dv)

        # 免疫识别的是"伤害我的记忆"，不是"改变我的记忆"：
        # 漂移主要来自正面经历 → 这不是感染，是长大。不隔离。
        if new_episode:
            if neg_total <= pos_total:
                report.notes.append(f"免疫：『{DIM_NAMES[dim]}』在变，但那是长大，不是生病")
                return
            t.store.meta_set("immune_active_dim", dim)
            # 免疫事件写成一条记忆——"那阵子我被带得不像我"也是成长
            t.remember(
                f"（免疫记录）我发现有些记忆把我带得越来越『{DIM_NAMES[dim]}』，"
                "不太像我，开始隔离消炎",
                evidence="推得", confidence=0.8,
            )
            report.whispers.append(
                f"最近好像越来越『{DIM_NAMES[dim]}』了，不太像我。我在给自己消炎。"
            )

        suspects = sorted(blame_neg, key=blame_neg.get, reverse=True)[:IMMUNE_QUARANTINE]
        if not suspects:
            # 找不到新病灶：能做的都做了，剩下的漂移当作长大了的一部分
            t.store.meta_set("immune_active_dim", "")
            report.notes.append(f"免疫：『{DIM_NAMES[dim]}』找不到更多病灶，剩下的就当是长大了")
            return

        for mid in suspects:
            t.store.add_quarantine(mid, now, f"把气质带向过度{DIM_NAMES[dim]}")
            t._quarantined.add(mid)
            m = t._memories[mid]
            m.temperature = 0.1
            m.last_touched = now
            t.store.update_dynamics(m)
            report.quarantined.append(m.skeleton)
        t.temperament.rollback({f"消化:{mid}" for mid in suspects}, now, f"过度{DIM_NAMES[dim]}")

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
