"""过往记忆导入——不是灌数据库，是让它把旧日子重新活一遍。

支持两种来源：
1. claude.ai 的数据导出（conversations.json）：
   claude.ai → 设置 → 隐私 → 导出数据 → 邮箱收到 zip → 解压得 conversations.json
2. 一个文件夹的 .txt / .md 对话记录（每个文件一段对话，文件修改时间当日期）

导入方式：按时间顺序重放——时钟跳到每段对话的原始日期写入记忆，
中间的空档一天一天睡过去（消化、做梦、长性格都在这些"夜里"真实发生）。
所以导入完的它不是一个塞满数据的库，而是一个已经把这些日子消化过的存在：
老对话自然是冷的、沉底的，动过感情的沉淀成了气质。

设了 TURU_LLM_CMD（如 claude -p）时，每段对话由它自己重读并提炼成 1-3 条
值得留住的记忆（带感受）；没设则用朴素规则截取。重复导入自动去重。

用法：python turu/importer.py <conversations.json 或 文件夹> [记忆库路径]
"""

import datetime
import glob
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from turu.clock import Clock  # noqa: E402
from turu.llm import llm_from_env  # noqa: E402
from turu.turu import Turu  # noqa: E402

DAY = 86400.0
MAX_TEXT = 6000  # 喂给 LLM 的单段对话截断长度


def _ts(iso: str) -> float:
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def parse_claude_export(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    convs = []
    for c in data:
        msgs = c.get("chat_messages") or []
        if not msgs:
            continue
        at = _ts(c.get("created_at") or msgs[0].get("created_at") or "")
        if at <= 0:
            continue
        lines = []
        for m in msgs:
            who = "主人" if m.get("sender") == "human" else "我"
            text = (m.get("text") or "").strip()
            if text:
                lines.append(f"{who}：{text}")
        if not lines:
            continue
        convs.append({
            "id": c.get("uuid") or f"conv-{at}",
            "title": (c.get("name") or "").strip() or "（无题的一次对话）",
            "at": at,
            "text": "\n".join(lines),
        })
    return convs


def parse_folder(path: str) -> list[dict]:
    convs = []
    for fp in sorted(glob.glob(os.path.join(path, "*.txt")) + glob.glob(os.path.join(path, "*.md"))):
        with open(fp, encoding="utf-8", errors="replace") as f:
            text = f.read().strip()
        if not text:
            continue
        convs.append({
            "id": f"file-{os.path.basename(fp)}-{os.path.getsize(fp)}",
            "title": os.path.splitext(os.path.basename(fp))[0],
            "at": os.path.getmtime(fp),
            "text": text,
        })
    return convs


def distill(conv: dict, llm) -> list[dict]:
    """把一段旧对话提炼成 1-3 条记忆。有 LLM 时它自己重读，没有就朴素截取。"""
    if llm is not None:
        prompt = (
            "这是我过去和主人的一段对话记录，我在重读自己的旧日子。\n"
            "请从中提炼 1 到 3 条值得留住的记忆，一行一条，严格用这个格式：\n"
            "事实|感受1,感受2|我现在回头看的理解\n"
            "感受和理解可以留空但竖线要在。只输出这些行，不要别的。\n\n"
            f"【对话《{conv['title']}》】\n{conv['text'][:MAX_TEXT]}"
        )
        out = llm(prompt)
        if out:
            memories = []
            for line in out.splitlines():
                if "|" not in line:
                    continue
                parts = (line.strip().split("|") + ["", ""])[:3]
                skeleton = parts[0].strip()
                if not skeleton:
                    continue
                feelings = [x.strip() for x in parts[1].split(",") if x.strip()]
                memories.append({
                    "skeleton": skeleton,
                    "feelings": feelings,
                    "reading": parts[2].strip() or None,
                })
            if memories:
                return memories[:3]
    # 朴素回退：标题 + 头两句主人说的话当血肉
    date = datetime.datetime.fromtimestamp(conv["at"]).strftime("%Y-%m-%d")
    human = [ln[3:].strip() for ln in conv["text"].splitlines() if ln.startswith("主人：")]
    flesh = [h[:80] for h in human[:2] if h]
    return [{
        "skeleton": f"{date} 和主人聊过：{conv['title']}",
        "feelings": [],
        "reading": None,
        "flesh": flesh,
    }]


def run(source: str, db_path: str) -> dict:
    convs = (
        parse_claude_export(source) if os.path.isfile(source) else parse_folder(source)
    )
    convs.sort(key=lambda c: c["at"])
    if not convs:
        print("没读到任何对话。")
        return {"imported": 0, "slept": 0, "skipped": 0}

    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    clock = Clock(start=convs[0]["at"] - 3600.0)
    t = Turu(db_path, clock=clock)
    llm = llm_from_env()
    print(f"共 {len(convs)} 段旧日子，从 "
          f"{datetime.datetime.fromtimestamp(convs[0]['at']).strftime('%Y-%m-%d')} 开始重活一遍"
          f"{'（由它自己重读提炼）' if llm else '（朴素提炼；设 TURU_LLM_CMD 可让它自己重读）'}……")

    imported = slept = skipped = 0
    for i, conv in enumerate(convs, 1):
        if t.store.meta_get(f"imported:{conv['id']}"):
            skipped += 1
            continue
        # 空档的日子一天一天睡过去——消化和梦都真实发生
        while conv["at"] - clock.now() > DAY:
            clock.advance(days=1)
            if t.sleep() is not None:
                slept += 1
        clock.jump_to(conv["at"])
        for mm in distill(conv, llm):
            t.remember(
                mm["skeleton"],
                flesh=mm.get("flesh"),
                feelings=mm.get("feelings") or None,
                reading=mm.get("reading"),
            )
            imported += 1
        t.store.meta_set(f"imported:{conv['id']}", "1")
        if i % 20 == 0 or i == len(convs):
            print(f"  …活到第 {i}/{len(convs)} 段（已记 {imported} 条，睡了 {slept} 晚）")

    # 收尾：最后睡一觉，把最近的日子也消化了
    if t.sleep(force=True) is not None:
        slept += 1
    layers = {k: len(v) for k, v in t.layers().items()}
    print(f"\n导入完成：记住 {imported} 条（跳过已导入 {skipped} 段），睡了 {slept} 晚。")
    print(f"记忆分层：烫 {layers['烫']} / 温 {layers['温']} / 冷 {layers['冷']}"
          f"——老日子自然沉底了，这是对的。")
    print("看看它现在的性子：python examples/timeline.py")
    t.close()
    return {"imported": imported, "slept": slept, "skipped": skipped}


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return
    default_db = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "turu.db"
    )
    db = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("TURU_DB", default_db)
    run(sys.argv[1], db)


if __name__ == "__main__":
    main()
