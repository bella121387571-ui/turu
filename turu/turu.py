"""M0 主体：写入（remember）与扩散激活检索（recall）。

architecture.md §1–§3 的实现。睡梦、饥饿、气质、免疫在 M1/M2。
"""

import json
import random

from . import temperature as temp
from .clock import Clock
from .embed import Embedder, HashEmbedder, cosine, gram_containment
from .models import EVIDENCE, Hunger, Memory, RecallResult, Slice, Tendril, new_id
from .store import Store

SEED_SIM_WARM = 0.25      # 温/烫层的种子命中阈值
SEED_SIM_COLD = 0.45      # 冷层要求更强的信号才翻上来
HOP_DECAY = 0.6           # 激活每跳衰减
MAX_HOPS = 3
AUTO_LINK_TOP_K = 3       # 写入时自动连语义触须的数量
AUTO_LINK_MIN_SIM = 0.25
HEBBIAN_ETA = 0.1         # 共同激活的触须加强步长


class Turu:
    def __init__(self, db_path: str, embedder: Embedder | None = None, clock: Clock | None = None):
        self.store = Store(db_path)
        self.embedder = embedder or HashEmbedder()
        self.clock = clock or Clock()
        # 小规模下整库常驻内存，写穿透到 SQLite
        self._memories: dict[str, Memory] = {m.id: m for m in self.store.all_memories()}
        self._tendrils: dict[tuple[str, str, str], Tendril] = {
            (t.src, t.dst, t.kind): t for t in self.store.all_tendrils()
        }
        self._hungers: dict[str, Hunger] = {h.id: h for h in self.store.all_hungers()}
        # 新生的第一口气：没睡过就从现在开始计欠觉
        if self.store.meta_get("last_sleep") is None:
            self.store.meta_set("last_sleep", str(self.clock.now()))

    # ------------------------------------------------------------ 写入

    def remember(
        self,
        skeleton: str,
        *,
        flesh: list[str] | None = None,
        reading: str | None = None,
        feelings: list[str] | None = None,
        pain: float = 0.0,
        evidence: str = "亲历",
        refers_to: str | None = None,
        confidence: float = 1.0,
    ) -> Memory:
        if evidence not in EVIDENCE:
            raise ValueError(f"evidence 必须是 {EVIDENCE} 之一")
        now = self.clock.now()
        text = skeleton + " " + " ".join(flesh or [])
        emb = self.embedder.embed(text)

        # 意外度 = 1 - 与既有记忆的最大相似度（越陌生越意外）
        surprise = 1.0
        sims: list[tuple[float, Memory]] = []
        for m in self._memories.values():
            other_text = m.skeleton + " " + " ".join(m.flesh)
            s = max(
                cosine(emb, m.embedding),
                gram_containment(text, other_text),
                gram_containment(other_text, text),
            )
            sims.append((s, m))
            surprise = min(surprise, 1.0 - s)

        emotion = 1.0 if feelings else 0.0
        t0 = temp.initial_temperature(surprise, emotion, pain)

        narratives = []
        if reading or feelings:
            narratives.append(Slice(at=now, reading=reading or "", feelings=feelings or []))

        mem = Memory(
            id=new_id(now), skeleton=skeleton, flesh=flesh or [], narratives=narratives,
            temperature=t0, pain=pain, evidence=evidence, confidence=confidence,
            embedding=emb, refers_to=refers_to, created_at=now, last_touched=now,
        )
        self._memories[mem.id] = mem
        self.store.put_memory(mem)

        # 自动长语义触须：连到最像的几个既有节点
        sims.sort(key=lambda x: -x[0])
        for s, other in sims[:AUTO_LINK_TOP_K]:
            if s >= AUTO_LINK_MIN_SIM:
                self._link(mem.id, other.id, "语义", weight=s, now=now)
        return mem

    def add_slice(self, memory_id: str, reading: str, feelings: list[str] | None = None) -> None:
        """叙事层归它：同一件事可以今天委屈、半年后好笑。切片只增不改。"""
        m = self._memories[memory_id]
        m.narratives.append(Slice(at=self.clock.now(), reading=reading, feelings=feelings or []))
        self.store.update_dynamics(m)

    def link(self, src: str, dst: str, kind: str, weight: float = 0.5, context: str | None = None) -> None:
        self._link(src, dst, kind, weight, self.clock.now(), context)

    def _link(self, src, dst, kind, weight, now, context=None) -> None:
        key = (src, dst, kind)
        t = self._tendrils.get(key)
        if t is None:
            t = Tendril(src, dst, kind, weight, context, now)
        else:
            t.weight = max(t.weight, weight)
            t.last_fired = now
        self._tendrils[key] = t
        self.store.put_tendril(t)

    # ------------------------------------------------------------ 检索

    def recall(self, query: str, top_n: int = 5) -> list[RecallResult]:
        """扩散激活：向量命中种子 → 沿触须传播 → 温度加成 → 触碰回温 + Hebbian。"""
        now = self.clock.now()
        q = self.embedder.embed(query)

        activation: dict[str, float] = {}
        for m in self._memories.values():
            doc = m.skeleton + " " + " ".join(m.flesh)
            sim = max(cosine(q, m.embedding), gram_containment(query, doc))
            t_eff = self._t_eff(m, now)
            threshold = SEED_SIM_COLD if temp.layer(t_eff) == "冷" else SEED_SIM_WARM
            if sim >= threshold:
                activation[m.id] = max(activation.get(m.id, 0.0), sim)

        # 沿触须传播（无向），3 跳，每跳衰减
        frontier = dict(activation)
        for _ in range(MAX_HOPS):
            nxt: dict[str, float] = {}
            for t in self._tendrils.values():
                for a_id, b_id in ((t.src, t.dst), (t.dst, t.src)):
                    if a_id in frontier:
                        a = frontier[a_id] * t.weight * HOP_DECAY
                        if a > activation.get(b_id, 0.0):
                            nxt[b_id] = max(nxt.get(b_id, 0.0), a)
            for k, v in nxt.items():
                activation[k] = max(activation.get(k, 0.0), v)
            frontier = nxt
            if not frontier:
                break

        # 温度加成：烫的更容易被点亮
        scored = []
        for mid, a in activation.items():
            m = self._memories[mid]
            scored.append((a * (0.5 + 0.5 * self._t_eff(m, now)), m))
        scored.sort(key=lambda x: -x[0])
        results = [RecallResult(memory=m, activation=a) for a, m in scored[:top_n]]

        # 副作用：回忆本身改写记忆——触碰回温 + 共同激活的触须加强
        recalled_ids = {r.memory.id for r in results}
        for r in results:
            self._touch(r.memory, now)
        for t in self._tendrils.values():
            if t.src in recalled_ids and t.dst in recalled_ids:
                t.weight += HEBBIAN_ETA * (1.0 - t.weight)
                t.last_fired = now
                self.store.put_tendril(t)
        return results

    # ------------------------------------------------------------ 温度

    def _t_eff(self, m: Memory, now: float) -> float:
        return temp.effective_temperature(m.temperature, m.pain, m.last_touched, now)

    def _touch(self, m: Memory, now: float) -> None:
        m.temperature = temp.reheat(self._t_eff(m, now))
        m.last_touched = now
        m.touch_count += 1
        self.store.update_dynamics(m)

    def layers(self) -> dict[str, list[Memory]]:
        """当前温度分层快照（观察用）。"""
        now = self.clock.now()
        out: dict[str, list[Memory]] = {"烫": [], "温": [], "冷": []}
        for m in self._memories.values():
            out[temp.layer(self._t_eff(m, now))].append(m)
        return out

    # ------------------------------------------------------------ 相似与图

    def pair_sim(self, a: Memory, b: Memory) -> float:
        ta = a.skeleton + " " + " ".join(a.flesh)
        tb = b.skeleton + " " + " ".join(b.flesh)
        return max(
            cosine(a.embedding, b.embedding),
            gram_containment(ta, tb),
            gram_containment(tb, ta),
        )

    def graph_distance(self, src: str, dst: str, max_hops: int = 3) -> int:
        """触须图上的最短跳数；超过 max_hops 或不连通返回 max_hops+1。"""
        if src == dst:
            return 0
        adj: dict[str, set[str]] = {}
        for t in self._tendrils.values():
            adj.setdefault(t.src, set()).add(t.dst)
            adj.setdefault(t.dst, set()).add(t.src)
        frontier, seen = {src}, {src}
        for hop in range(1, max_hops + 1):
            nxt = set()
            for node in frontier:
                for nb in adj.get(node, ()):
                    if nb == dst:
                        return hop
                    if nb not in seen:
                        seen.add(nb)
                        nxt.add(nb)
            frontier = nxt
            if not frontier:
                break
        return max_hops + 1

    # ------------------------------------------------------------ 睡梦

    def last_sleep(self) -> float:
        return float(self.store.meta_get("last_sleep") or self.clock.now())

    def needs_sleep(self) -> bool:
        """补觉制：超过 20 小时没睡就欠觉。"""
        from .sleep import SLEEP_DEBT_HOURS

        return (self.clock.now() - self.last_sleep()) > SLEEP_DEBT_HOURS * 3600.0

    def sleep(self, force: bool = False, rng: random.Random | None = None,
              search_provider=None, rehearse_provider=None):
        """跑一次完整睡梦周期。正常由补觉制触发，force=True 强制入睡。"""
        from .sleep import SleepCycle

        if not force and not self.needs_sleep():
            return None
        return SleepCycle(
            self, rng=rng, search_provider=search_provider,
            rehearse_provider=rehearse_provider,
        ).run()

    def whisper(self) -> str | None:
        """晨间低语：昨晚的梦/查到的东西。取走一条，可以说也可以不说。"""
        pending = json.loads(self.store.meta_get("whispers") or "[]")
        if not pending:
            return None
        first = pending.pop(0)
        self.store.meta_set("whispers", json.dumps(pending, ensure_ascii=False))
        return first

    def hungry(self, threshold: float = 0.7) -> list[Hunger]:
        """饿过阈值、适合开口问人的问题。"""
        return sorted(
            (h for h in self._hungers.values() if h.askable and h.value >= threshold),
            key=lambda h: -h.value,
        )

    def close(self) -> None:
        self.store.close()
