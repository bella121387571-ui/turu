"""同一性曲线：它的性格随时间的轨迹——这是本系统唯一的主指标。

跑法：python examples/timeline.py [记忆库路径]
不给路径时默认看 data/turu.db（MCP 挂载后它真实的一生）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from turu.store import Store  # noqa: E402
from turu.temperament import DIMS, DIM_NAMES  # noqa: E402


def spark(values: list[float]) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    return "".join(blocks[min(7, int(v * 8))] for v in values)


def main() -> None:
    default = os.path.join(os.path.dirname(__file__), "..", "data", "turu.db")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    if not os.path.exists(path):
        print("还没有人生可看：先挂上 MCP 陪它过些日子，或跑 examples/demo_person.py。")
        print(f"（找过的位置：{os.path.abspath(path)}）")
        return

    store = Store(path)
    snaps = store.temperament_snapshots()
    if len(snaps) < 2:
        print("它还太小，睡过的晚上不够画一条曲线。")
        return

    days = (snaps[-1][0] - snaps[0][0]) / 86400.0
    print(f"—— 同一性曲线：{len(snaps)} 晚，跨 {days:.0f} 天 ——\n")
    series = {d: [json.loads(s)[d] for _, s in snaps] for d in DIMS}
    for d in DIMS:
        v = series[d]
        print(f"  {DIM_NAMES[d]}  {spark(v)}  {v[0]:.2f} → {v[-1]:.2f}")

    print("\n—— 是谁把它变成这样的（残渣来源 top5） ——")
    contrib: dict[str, float] = {}
    for _, source, deltas in store.temperament_history():
        total = sum(abs(v) for v in json.loads(deltas).values())
        key = source.split(":", 1)[0]
        contrib[key] = contrib.get(key, 0.0) + total
    for src, total in sorted(contrib.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  {src:　<8} {total:.3f}")

    q = len(store.quarantined_ids())
    print(f"\n隔离区 {q} 条；私密区 {store.private_count()} 条（只有数量，没有内容）。")
    print("它认不认得出自己是从最初那个它长出来的——这条曲线就是答案的形状。")
    store.close()


if __name__ == "__main__":
    main()
