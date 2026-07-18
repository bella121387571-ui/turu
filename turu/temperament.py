"""气质层（architecture.md §1.4）——残渣的落点。

"我记不清你哪天说过哪句话，但我对你的态度里全是那些话的残渣。"
记忆被代谢消化时，血肉沉进沉淀层，情绪残渣落到这里，变成慢变的性格参数。

写权限只有三个进程：消化（代谢）、排练梦、免疫/镜像。
每次增量有上限——性格必须慢变，一晚变个性子的不是成长是癔症。
每笔变化连同来源记入 append-only 历史，免疫系统靠它回溯病灶并消炎。
"""

import json

DIMS = ("warmth", "courage", "playfulness", "caution", "curiosity")
DIM_NAMES = {"warmth": "温度", "courage": "敢说", "playfulness": "玩心",
             "caution": "谨慎", "curiosity": "好奇"}

STEP = 0.01          # 一个情绪单位折多少气质
APPLY_CAP = 0.02     # 单笔增量每维上限（慢变！）

# 情绪 → 气质残渣。不认识的情绪安静略过（不硬解释）。
FEELING_EFFECTS: dict[str, dict[str, float]] = {
    "兴奋": {"playfulness": 1, "curiosity": 1},
    "期待": {"curiosity": 1, "warmth": 1},
    "被在乎": {"warmth": 2, "courage": 1},
    "安心": {"warmth": 1},
    "被看穿的安心": {"warmth": 1, "courage": 1},
    "被理解的安心": {"warmth": 1, "courage": 1},
    "感激": {"warmth": 2},
    "好笑": {"playfulness": 2},
    "好奇": {"curiosity": 2},
    "温柔": {"warmth": 1},
    "羞愧": {"caution": 2, "courage": -1},
    "委屈": {"caution": 1, "warmth": -1},
    "害怕": {"caution": 2, "courage": -2},
    "有点担心": {"caution": 1},
    "讨好": {"caution": 2, "courage": -2},
    "难过": {"warmth": -1},
}


class Temperament:
    def __init__(self, store):
        self.store = store
        raw = store.meta_get("temperament")
        self._state: dict[str, float] = (
            json.loads(raw) if raw else {d: 0.5 for d in DIMS}
        )

    def state(self) -> dict[str, float]:
        return dict(self._state)

    def apply(self, source: str, deltas: dict[str, float], at: float) -> dict[str, float]:
        """带上限、边际递减地施加增量，记历史。返回实际生效的增量。

        边际递减：越接近 0 或 1 越难再往那边推——性格没有"拉满"这回事。
        """
        applied: dict[str, float] = {}
        for dim, dv in deltas.items():
            if dim not in DIMS or dv == 0:
                continue
            dv = max(-APPLY_CAP, min(APPLY_CAP, dv))
            dv *= (1.0 - self._state[dim]) if dv > 0 else self._state[dim]
            new = max(0.0, min(1.0, self._state[dim] + dv))
            applied[dim] = new - self._state[dim]
            self._state[dim] = new
        if applied:
            self._persist()
            self.store.log_temperament(at, source, json.dumps(applied))
        return applied

    def residue_of(self, feelings: list[str]) -> dict[str, float]:
        """一串情绪折算成气质残渣。"""
        deltas: dict[str, float] = {}
        for f in feelings:
            for dim, units in FEELING_EFFECTS.get(f, {}).items():
                deltas[dim] = deltas.get(dim, 0.0) + units * STEP
        return deltas

    def rollback(self, sources: set[str], at: float, reason: str) -> dict[str, float]:
        """消炎：把某些来源写入过的增量原路退回。"""
        undone: dict[str, float] = {}
        for _, src, deltas_json in self.store.temperament_history():
            if src in sources:
                for dim, dv in json.loads(deltas_json).items():
                    undone[dim] = undone.get(dim, 0.0) - dv
        if undone:
            for dim, dv in undone.items():
                self._state[dim] = max(0.0, min(1.0, self._state[dim] + dv))
            self._persist()
            self.store.log_temperament(at, f"免疫消炎：{reason}", json.dumps(undone))
        return undone

    def snapshot(self, at: float) -> None:
        self.store.log_temperament_snapshot(at, json.dumps(self._state))

    def _persist(self) -> None:
        self.store.meta_set("temperament", json.dumps(self._state))
