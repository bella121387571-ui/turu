"""温度动力学（architecture.md §2）。

温度只影响可及性，不影响存在性——骨架永远在。
"""

import math

from .clock import DAY

LAMBDA_BASE = 0.05  # 每天的基础衰减率：普通记忆约两周降到一半
ALPHA = 0.3         # 触碰回温步长
HOT = 0.7           # 烫层下界
COLD = 0.3          # 冷层上界


def initial_temperature(surprise: float, emotion: float, pain: float) -> float:
    if pain > 0:
        return 1.0  # 疼痛记忆直接烫透
    t = 0.3 + 0.4 * surprise + 0.3 * emotion
    return max(0.0, min(1.0, t))


def effective_temperature(stored_t: float, pain: float, last_touched: float, now: float) -> float:
    """惰性衰减：读的时候按距上次触碰的天数现算。"""
    days = max(0.0, (now - last_touched) / DAY)
    lam = LAMBDA_BASE * (1.0 - 0.9 * pain)  # 疼过的冷得极慢
    return stored_t * math.exp(-lam * days)


def reheat(t: float) -> float:
    return t + ALPHA * (1.0 - t)


def layer(t: float) -> str:
    if t > HOT:
        return "烫"
    if t >= COLD:
        return "温"
    return "冷"
