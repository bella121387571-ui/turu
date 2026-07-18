"""SQLite 持久化。整个记忆库 = 一个文件，放哪个盘都行。

骨架事实的锁死在这里由结构保证：本模块不提供任何改写 skeleton 的语句；
血肉的"消化"是把条目移入 digested_flesh（沉淀，不再可检索），不做物理删除。
"""

import json
import sqlite3

from .models import Memory, Slice, Tendril, slices_from_json, slices_to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id           TEXT PRIMARY KEY,
  skeleton     TEXT NOT NULL,
  flesh        TEXT NOT NULL,
  narratives   TEXT NOT NULL,
  temperature  REAL NOT NULL,
  pain         REAL NOT NULL,
  evidence     TEXT NOT NULL,
  confidence   REAL NOT NULL,
  embedding    TEXT NOT NULL,
  refers_to    TEXT,
  created_at   REAL NOT NULL,
  last_touched REAL NOT NULL,
  touch_count  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS tendrils (
  src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL,
  weight REAL NOT NULL, context TEXT, last_fired REAL NOT NULL,
  PRIMARY KEY (src, dst, kind)
);
CREATE TABLE IF NOT EXISTS digested_flesh (   -- 消化沉淀层：遗忘不是删除
  memory_id TEXT NOT NULL, detail TEXT NOT NULL, digested_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- memories ----

    def put_memory(self, m: Memory) -> None:
        self.conn.execute(
            "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                m.id, m.skeleton, json.dumps(m.flesh, ensure_ascii=False),
                slices_to_json(m.narratives), m.temperature, m.pain, m.evidence,
                m.confidence, json.dumps(m.embedding), m.refers_to,
                m.created_at, m.last_touched, m.touch_count,
            ),
        )
        self.conn.commit()

    def update_dynamics(self, m: Memory) -> None:
        """只允许更新动态字段：温度、触碰、叙事、血肉。skeleton 不在其中。"""
        self.conn.execute(
            "UPDATE memories SET flesh=?, narratives=?, temperature=?,"
            " last_touched=?, touch_count=? WHERE id=?",
            (
                json.dumps(m.flesh, ensure_ascii=False), slices_to_json(m.narratives),
                m.temperature, m.last_touched, m.touch_count, m.id,
            ),
        )
        self.conn.commit()

    def all_memories(self) -> list[Memory]:
        rows = self.conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_memory(r) for r in rows]

    @staticmethod
    def _row_to_memory(r: tuple) -> Memory:
        return Memory(
            id=r[0], skeleton=r[1], flesh=json.loads(r[2]),
            narratives=slices_from_json(r[3]), temperature=r[4], pain=r[5],
            evidence=r[6], confidence=r[7], embedding=json.loads(r[8]),
            refers_to=r[9], created_at=r[10], last_touched=r[11], touch_count=r[12],
        )

    # ---- tendrils ----

    def put_tendril(self, t: Tendril) -> None:
        self.conn.execute(
            "INSERT INTO tendrils VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(src,dst,kind) DO UPDATE SET weight=excluded.weight,"
            " last_fired=excluded.last_fired",
            (t.src, t.dst, t.kind, t.weight, t.context, t.last_fired),
        )
        self.conn.commit()

    def all_tendrils(self) -> list[Tendril]:
        rows = self.conn.execute("SELECT * FROM tendrils").fetchall()
        return [Tendril(*r) for r in rows]

    # ---- digestion (M1 会用到，M0 先把沉淀层建好) ----

    def digest_flesh(self, memory_id: str, detail: str, now: float) -> None:
        self.conn.execute(
            "INSERT INTO digested_flesh VALUES (?,?,?)", (memory_id, detail, now)
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
