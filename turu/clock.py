"""可注入的时钟。

模拟器需要快进时间（睡几晚、过几个月），所以整个系统不直接用 time.time()，
而是从 Clock 拿现在几点。真实运行时它就是墙上时钟。
"""

import time

DAY = 86400.0


class Clock:
    def __init__(self, start: float | None = None):
        self._offset = 0.0
        self._fixed_start = start

    def now(self) -> float:
        base = self._fixed_start if self._fixed_start is not None else time.time()
        return base + self._offset

    def advance(self, days: float = 0.0, hours: float = 0.0) -> None:
        self._offset += days * DAY + hours * 3600.0

    def jump_to(self, ts: float) -> None:
        """跳到某个绝对时刻（导入旧记忆时按原始日期重活一遍用）。"""
        base = self._fixed_start if self._fixed_start is not None else time.time()
        self._offset = ts - base
