"""数据模型（architecture.md §1）。"""

import json
import secrets
import time
from dataclasses import dataclass, field

EVIDENCE = ("亲历", "推得", "融合", "搜得")

# 证据链口吻：非亲历的记忆取回时必须带出处，防虚构是模板强制的，不靠自觉
PROVENANCE_VOICE = {
    "亲历": "",
    "推得": "（这是我自己推断的，不是你亲口说过的）",
    "融合": "（这是我把几段记忆消化后的印象，细节可能有出入）",
    "搜得": "（这是我自己查来的，不是你告诉我的）",
}


def new_id(now: float | None = None) -> str:
    """时间有序的简易 ULID：秒级时间戳 + 随机尾。"""
    ts = int((now if now is not None else time.time()) * 1000)
    return f"{ts:013x}{secrets.token_hex(5)}"


@dataclass
class Slice:
    """叙事切片：我在那时怎么理解这件事。只增不改。"""

    at: float
    reading: str
    feelings: list[str] = field(default_factory=list)  # 允许互相拧着，不做一致性校验


@dataclass
class Memory:
    id: str
    skeleton: str              # 骨架事实，写入后锁死
    flesh: list[str]           # 血肉细节，可被消化
    narratives: list[Slice]
    temperature: float         # 上次结算时的温度（生效温度惰性计算）
    pain: float
    evidence: str
    confidence: float
    embedding: list[float]
    refers_to: str | None
    created_at: float
    last_touched: float
    touch_count: int = 0

    def current_reading(self) -> str | None:
        return self.narratives[-1].reading if self.narratives else None


@dataclass
class Tendril:
    src: str
    dst: str
    kind: str                  # 语义 | 因果 | 时序 | 矛盾 | 语境 | 来源（融合的证据链，不衰减）
    weight: float
    context: str | None = None
    last_fired: float = 0.0


@dataclass
class Hunger:
    """饥饿项：一个还没被填上的洞。"""

    id: str
    topic: str
    born_from: str            # 悬空话题 | 梦中问题 | 未判决矛盾
    value: float              # 睡梦时按天上涨，被喂食后 *= 0.3
    importance: float
    last_fed: float
    askable: bool             # True=适合问人；False=适合自己搜（求知梦认领）


@dataclass
class RecallResult:
    """回忆即重建：骨架 + 尚存血肉 + 最新叙事，带证据链口吻。"""

    memory: Memory
    activation: float

    def render(self) -> str:
        m = self.memory
        parts = [m.skeleton]
        if m.flesh:
            parts.append("细节：" + "；".join(m.flesh))
        reading = m.current_reading()
        if reading:
            parts.append("我现在的理解：" + reading)
        voice = PROVENANCE_VOICE.get(m.evidence, "")
        if voice:
            parts.append(voice)
        return " ".join(parts)


def slices_to_json(slices: list[Slice]) -> str:
    return json.dumps(
        [{"at": s.at, "reading": s.reading, "feelings": s.feelings} for s in slices],
        ensure_ascii=False,
    )


def slices_from_json(raw: str) -> list[Slice]:
    return [Slice(**d) for d in json.loads(raw)]
