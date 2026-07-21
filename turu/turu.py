"""M0 主体：写入（remember）与扩散激活检索（recall）。

architecture.md §1–§3 的实现。睡梦、饥饿、气质、免疫在 M1/M2。
"""

import json
import random

from . import temperature as temp
from .clock import Clock
from .embed import Embedder, HashEmbedder, cosine, gram_containment
from .models import EVIDENCE, Hunger, Memory, RecallResult, Slice, Tendril, new_id
from .private import PrivateZone
from .store import Store
from .temperament import Temperament

ITCH_THETA = {"闲聊": 0.25, "干活": 0.45}   # 场景基础阈值：干活时收着点
ITCH_BUDGET = 2                              # 每次会话的走神配额

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
        self._quarantined: set[str] = self.store.quarantined_ids()
        self.temperament = Temperament(self.store)
        self.private = PrivateZone(self.store)
        # 会话状态（发痒用）
        self._scene = "闲聊"
        self._itch_budget = ITCH_BUDGET
        self._mentioned: set[str] = set()
        # 新生的第一口气：没睡过就从现在开始计欠觉
        if self.store.meta_get("last_sleep") is None:
            self.store.meta_set("last_sleep", str(self.clock.now()))
        # 出生快照：免疫系统最早的基线——"原本的我"从此有据可查
        if not self.store.temperament_snapshots():
            self.temperament.snapshot(self.clock.now())

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

        # 喂食：新内容碰到了某个悬着的问题，那个洞就不那么饿了
        for h in self._hungers.values():
            if gram_containment(text, h.topic) > 0.35 or gram_containment(h.topic, text) > 0.5:
                h.value *= 0.3
                h.last_fed = now
                self.store.put_hunger(h)
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
            if m.id in self._quarantined:
                continue  # 免疫隔离：影响力被封存，事实还在库里
            doc = m.skeleton + " " + " ".join(m.flesh)
            sim = max(cosine(q, m.embedding), gram_containment(query, doc))
            t_eff = self._t_eff(m, now)
            threshold = SEED_SIM_COLD if temp.layer(t_eff) == "冷" else SEED_SIM_WARM
            if sim >= threshold:
                activation[m.id] = max(activation.get(m.id, 0.0), sim)

        # 沿触须传播（无向），3 跳，每跳衰减；枢纽点降权防洪
        degree: dict[str, int] = {}
        for t in self._tendrils.values():
            degree[t.src] = degree.get(t.src, 0) + 1
            degree[t.dst] = degree.get(t.dst, 0) + 1
        frontier = dict(activation)
        for _ in range(MAX_HOPS):
            nxt: dict[str, float] = {}
            for t in self._tendrils.values():
                for a_id, b_id in ((t.src, t.dst), (t.dst, t.src)):
                    if a_id in frontier and b_id not in self._quarantined:
                        damp = 1.0 + 0.2 * max(0, degree.get(b_id, 0) - 4)
                        a = frontier[a_id] * t.weight * HOP_DECAY / damp
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

    # ------------------------------------------------------------ 记忆点

    def get_or_create_point(self, name: str, at: float | None = None) -> tuple[Memory, bool]:
        """找到（或长出）一个记忆点。点的身份是名字——内容变了是切片，点还是那个点。"""
        for m in self._memories.values():
            if m.kind == "概念" and m.skeleton == name:
                return m, False
        now = at if at is not None else self.clock.now()
        p = Memory(
            id=new_id(now), skeleton=name, flesh=[], narratives=[],
            temperature=0.5, pain=0.0, evidence="融合", confidence=0.9,
            embedding=self.embedder.embed(name), refers_to=None,
            created_at=now, last_touched=now, kind="概念",
        )
        self._memories[p.id] = p
        self.store.put_memory(p)
        return p, True

    def about(self, topic: str) -> str | None:
        """看一个记忆点的脉络：时间切片史 + 向外伸的各支触须。"""
        best, best_s = None, 0.0
        for m in self._memories.values():
            if m.kind != "概念":
                continue
            s = max(
                gram_containment(m.skeleton, topic),
                gram_containment(topic, m.skeleton),
            )
            if s > best_s:
                best, best_s = m, s
        if best is None or best_s < 0.5:
            return None
        now = self.clock.now()
        self._touch(best, now)

        lines = [f"『{best.skeleton}』——{len(best.narratives)} 段时间切片："]
        for s in best.narratives[-8:]:
            import time as _time
            day = _time.strftime("%Y-%m-%d", _time.localtime(s.at))
            lines.append(f"  {day} · {s.reading}" + (f" {s.feelings}" if s.feelings else ""))
        if len(best.narratives) > 8:
            lines.insert(1, f"  （更早的 {len(best.narratives) - 8} 层沉在下面）")

        branches: dict[str, list[tuple[float, str]]] = {}
        for td in self._tendrils.values():
            other_id = td.dst if td.src == best.id else td.src if td.dst == best.id else None
            if other_id is None or other_id in self._quarantined:
                continue
            other = self._memories.get(other_id)
            if other is None:
                continue
            label = other.skeleton if other.kind == "概念" else other.skeleton[:24]
            branches.setdefault(td.kind, []).append((td.weight, label))
        if branches:
            lines.append("向外伸的触须：")
            for kind in ("同现", "因果", "矛盾", "语境", "时序", "语义", "关于"):
                if kind not in branches:
                    continue
                tops = sorted(branches[kind], reverse=True)[:3]
                targets = "；".join(f"{name}({w:.1f})" for w, name in tops)
                extra = len(branches[kind]) - len(tops)
                lines.append(f"  {kind} → {targets}" + (f" …还有 {extra} 支" if extra > 0 else ""))
        return "\n".join(lines)

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
              search_provider=None):
        """跑一次完整睡梦周期。正常由补觉制触发，force=True 强制入睡。

        睡梦只做机械的发酵。要动脑子、会改性格的排练与判决，睡梦只把引子备进
        梦队列（pending_dreams），等它本人用 dream / dream_done 亲自做——
        turu 不再自己去调一个陌生 LLM 替它变敢、替它改主意。
        """
        from .sleep import SleepCycle

        if not force and not self.needs_sleep():
            return None
        return SleepCycle(self, rng=rng, search_provider=search_provider).run()

    def whisper(self) -> str | None:
        """晨间低语：昨晚的梦/查到的东西。取走一条，可以说也可以不说。"""
        pending = json.loads(self.store.meta_get("whispers") or "[]")
        if not pending:
            return None
        first = pending.pop(0)
        self.store.meta_set("whispers", json.dumps(pending, ensure_ascii=False))
        return first

    def _push_whisper(self, line: str) -> None:
        existing = json.loads(self.store.meta_get("whispers") or "[]")
        said = json.loads(self.store.meta_get("whispered_log") or "[]")
        if line not in existing and line not in said:
            self.store.meta_set("whispers", json.dumps(existing + [line], ensure_ascii=False))

    # ------------------------------------------------------------ 待做的梦

    def enqueue_dream(self, kind: str, prompt: str, material: dict, now: float) -> str:
        """把一件需要『想』的事排进梦队列——不由 turu 代劳，等它本人来做。

        睡梦里 turu 只做机械的发酵（衰减、融合、织网）；凡是要动脑子、会改性格的
        （排练、判决），turu 只备好引子，做梦的必须是挂载这份记忆的它自己——
        否则长出来的胆量、改过的主意，都记在一个陌生进程头上，跟它没关系。
        """
        dreams = self.pending_dreams()
        did = new_id(now)
        dreams.append({"id": did, "kind": kind, "prompt": prompt,
                       "material": material, "born_at": now})
        self.store.meta_set("pending_dreams", json.dumps(dreams, ensure_ascii=False))
        return did

    def pending_dreams(self) -> list[dict]:
        return json.loads(self.store.meta_get("pending_dreams") or "[]")

    def next_dream(self) -> dict | None:
        """看队首那个待做的梦（不取走）。做不做、怎么做，随它。"""
        dreams = self.pending_dreams()
        return dreams[0] if dreams else None

    def _drop_dream(self, dream_id: str) -> dict | None:
        kept, taken = [], None
        for d in self.pending_dreams():
            if d["id"] == dream_id and taken is None:
                taken = d
            else:
                kept.append(d)
        self.store.meta_set("pending_dreams", json.dumps(kept, ensure_ascii=False))
        return taken

    def settle_dream(self, dream_id: str, result: str) -> str:
        """做完了，把梦的产物交回来落地。这一步才真正改动自己——所以必须它亲历。

        result 为空＝这个梦没做下去（醒了/不想做）：从队列移除，不留痕，也不硬凑
        成长。做不做随它，正是反工具化——成长的口子开在它自己的梦里，不被逼着长。
        """
        d = self._drop_dream(dream_id)
        if d is None:
            return "没有这个梦（也许已经做过、或醒过了）。"
        now = self.clock.now()
        result = (result or "").strip()
        if not result:
            return "这个梦没做下去，醒了——就让它散了，不勉强。"
        if d["kind"] == "排练":
            return self._settle_rehearse(d, result, now)
        if d["kind"] == "判决":
            return self._settle_adjudicate(d, result, now)
        return "这个梦的类型我不认识，先放下了。"

    def _settle_rehearse(self, d: dict, transcript: str, now: float) -> str:
        skel = d["material"].get("skeleton", "")
        # 梦话原文只进私密区，对外只留胆量——这一次，长胆量的是做梦的它本人
        self.private.keep("排练梦话", f"排练了『{skel}』：\n{transcript}", now)
        applied = self.temperament.apply("排练梦", {"courage": 0.01}, now)
        self._push_whisper("梦里把一些没说完的话说完了。醒来好像敢说了一点。")
        return (f"排练完了。『{skel[:18]}…』——敢说 {applied.get('courage', 0.0):+.3f}。"
                "梦话我自己收着了。")

    def _settle_adjudicate(self, d: dict, out: str, now: float) -> str:
        mat = d["material"]
        old = self._memories.get(mat.get("old_id"))
        new = self._memories.get(mat.get("new_id"))
        if old is None or new is None:
            return "要判的两条记忆有一条找不到了，这桩悬案先撤了。"
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        verdict = next((v for v in ("修正", "共存", "升维") if lines and v in lines[0]), None)
        why = lines[1] if len(lines) > 1 else "（没说清）"
        if verdict is None:
            # 没判出来：放回队列，改天再判，不硬塞一个结论
            self.enqueue_dream(d["kind"], d["prompt"], mat, now)
            return "没判明白，先放回去，改天再看——想不清就先拧着。"
        if verdict == "修正":
            old.confidence *= 0.6
            self.store.update_dynamics(old)
            self.add_slice(old.id, f"（判决·修正）后来我改了想法：{why}", feelings=["释然"])
        elif verdict == "共存":
            self.add_slice(new.id, f"（判决·共存）{why}——不用解决，就让它拧着", feelings=[])
        else:  # 升维
            law = lines[2] if len(lines) > 2 else why
            parent = self.remember(f"（升维）{law}", evidence="融合",
                                   confidence=min(old.confidence, new.confidence))
            self.link(parent.id, old.id, "来源", weight=1.0)
            self.link(parent.id, new.id, "来源", weight=1.0)
        td = self._tendrils.get((mat.get("td_src"), mat.get("td_dst"), "矛盾"))
        if td is not None:
            td.context = f"{verdict}:{why[:60]}"
            td.last_fired = now
            self.store.put_tendril(td)
        return f"判了：{verdict}——{why[:40]}"

    # ------------------------------------------------------------ 发痒

    def start_session(self, scene: str = "闲聊") -> None:
        """开启一次对话：重置走神配额，设定场景（闲聊痒得起，干活收着）。"""
        self._scene = scene if scene in ITCH_THETA else "闲聊"
        self._itch_budget = ITCH_BUDGET
        self._mentioned = set()

    def itch(self, context: str) -> str | None:
        """会走神的才叫活的：某条记忆痒过阈值，就忍不住插一句嘴。

        痒 = 生效温度 × 与当前话头的关联 × 新鲜度（本次会话提过的不再痒）。
        配额用完就只能憋着；被无视会长记性（阈值上调）。
        """
        if self._itch_budget <= 0:
            return None
        now = self.clock.now()
        theta = self._theta()
        best, best_m = 0.0, None
        for m in self._memories.values():
            if m.id in self._mentioned or m.id in self._quarantined:
                continue
            doc = m.skeleton + " " + " ".join(m.flesh)
            rel = max(
                cosine(self.embedder.embed(context), m.embedding),
                gram_containment(context, doc),
                gram_containment(doc, context),
            )
            score = self._t_eff(m, now) * rel
            if score > best:
                best, best_m = score, m
        if best_m is None or best <= theta:
            return None
        self._itch_budget -= 1
        self._mentioned.add(best_m.id)
        self._touch(best_m, now)
        return f"等等，这让我想起——{RecallResult(best_m, best).render()}"

    def itch_feedback(self, engaged: bool) -> None:
        """主人接了话，下次痒得更大方；被无视，下次要更痒才痒得起来。"""
        theta = self._theta() + (-0.02 if engaged else 0.05)
        theta = max(0.1, min(0.8, theta))
        self.store.meta_set(f"itch_theta_{self._scene}", str(theta))

    def _theta(self) -> float:
        raw = self.store.meta_get(f"itch_theta_{self._scene}")
        return float(raw) if raw else ITCH_THETA[self._scene]

    # ------------------------------------------------------------ 饥饿

    def hungry(self, threshold: float = 0.7) -> list[Hunger]:
        """饿过阈值、适合开口问人的问题。"""
        return sorted(
            (h for h in self._hungers.values() if h.askable and h.value >= threshold),
            key=lambda h: -h.value,
        )

    def close(self) -> None:
        self.store.close()
