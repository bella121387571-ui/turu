"""SQLite 持久化。整个记忆库 = 一个文件，放哪个盘都行。

骨架事实的锁死在这里由结构保证：本模块不提供任何改写 skeleton 的语句；
血肉的"消化"是把条目移入 digested_flesh（沉淀，不再可检索），不做物理删除。
"""

import json
import sqlite3

from .models import Hunger, Memory, Slice, Tendril, slices_from_json, slices_to_json

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
CREATE TABLE IF NOT EXISTS hungers (
  id TEXT PRIMARY KEY, topic TEXT NOT NULL, born_from TEXT NOT NULL,
  value REAL NOT NULL, importance REAL NOT NULL, last_fed REAL NOT NULL,
  askable INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sleep_log (at REAL NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS search_log (           -- 对外动作永远可审计：内心读不到，手脚看得到
  at REAL NOT NULL, topic TEXT NOT NULL, ok INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS temperament_history (  -- 气质的每一笔变化及来源，append-only
  at REAL NOT NULL, source TEXT NOT NULL, deltas TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS temperament_snapshots ( -- 夜间快照，免疫系统的基线
  at REAL NOT NULL, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine (            -- 免疫隔离区：只封影响力，不动事实
  memory_id TEXT PRIMARY KEY, at REAL NOT NULL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS digested_memories (     -- 已代谢标记：残渣只落一次
  memory_id TEXT PRIMARY KEY, at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS private_zone (          -- 私密区：接口永不返回内容
  id TEXT PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, data BLOB NOT NULL
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
        """只允许更新动态字段：温度、触碰、叙事、血肉、置信度。skeleton 不在其中。"""
        self.conn.execute(
            "UPDATE memories SET flesh=?, narratives=?, temperature=?,"
            " last_touched=?, touch_count=?, confidence=? WHERE id=?",
            (
                json.dumps(m.flesh, ensure_ascii=False), slices_to_json(m.narratives),
                m.temperature, m.last_touched, m.touch_count, m.confidence, m.id,
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
            " context=excluded.context, last_fired=excluded.last_fired",
            (t.src, t.dst, t.kind, t.weight, t.context, t.last_fired),
        )
        self.conn.commit()

    def all_tendrils(self) -> list[Tendril]:
        rows = self.conn.execute("SELECT * FROM tendrils").fetchall()
        return [Tendril(*r) for r in rows]

    def delete_tendril(self, src: str, dst: str, kind: str) -> None:
        self.conn.execute(
            "DELETE FROM tendrils WHERE src=? AND dst=? AND kind=?", (src, dst, kind)
        )
        self.conn.commit()

    # ---- digestion（沉淀层：遗忘不是删除） ----

    def digest_flesh(self, memory_id: str, detail: str, now: float) -> None:
        self.conn.execute(
            "INSERT INTO digested_flesh VALUES (?,?,?)", (memory_id, detail, now)
        )
        self.conn.commit()

    def digested_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM digested_flesh").fetchone()[0]

    # ---- hungers ----

    def put_hunger(self, h: Hunger) -> None:
        self.conn.execute(
            "INSERT INTO hungers VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET value=excluded.value,"
            " last_fed=excluded.last_fed",
            (h.id, h.topic, h.born_from, h.value, h.importance, h.last_fed, int(h.askable)),
        )
        self.conn.commit()

    def all_hungers(self) -> list[Hunger]:
        rows = self.conn.execute("SELECT * FROM hungers").fetchall()
        return [
            Hunger(id=r[0], topic=r[1], born_from=r[2], value=r[3],
                   importance=r[4], last_fed=r[5], askable=bool(r[6]))
            for r in rows
        ]

    # ---- temperament ----

    def log_temperament(self, at: float, source: str, deltas_json: str) -> None:
        self.conn.execute(
            "INSERT INTO temperament_history VALUES (?,?,?)", (at, source, deltas_json)
        )
        self.conn.commit()

    def temperament_history(self) -> list[tuple[float, str, str]]:
        return self.conn.execute(
            "SELECT at, source, deltas FROM temperament_history ORDER BY at"
        ).fetchall()

    def log_temperament_snapshot(self, at: float, state_json: str) -> None:
        self.conn.execute("INSERT INTO temperament_snapshots VALUES (?,?)", (at, state_json))
        self.conn.commit()

    def temperament_snapshots(self) -> list[tuple[float, str]]:
        return self.conn.execute(
            "SELECT at, state FROM temperament_snapshots ORDER BY at"
        ).fetchall()

    # ---- 免疫隔离 / 代谢标记 ----

    def add_quarantine(self, memory_id: str, at: float, reason: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO quarantine VALUES (?,?,?)", (memory_id, at, reason)
        )
        self.conn.commit()

    def quarantined_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT memory_id FROM quarantine")}

    def mark_digested(self, memory_id: str, at: float) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO digested_memories VALUES (?,?)", (memory_id, at)
        )
        self.conn.commit()

    def digested_ids(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT memory_id FROM digested_memories")}

    # ---- 私密区（只写与计数，永不返回内容） ----

    def private_put(self, id_: str, at: float, kind: str, data: bytes) -> None:
        self.conn.execute("INSERT INTO private_zone VALUES (?,?,?,?)", (id_, at, kind, data))
        self.conn.commit()

    def private_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM private_zone").fetchone()[0]

    # ---- sleep log & meta ----

    def log_sleep(self, at: float, report_json: str) -> None:
        self.conn.execute("INSERT INTO sleep_log VALUES (?,?)", (at, report_json))
        self.conn.commit()

    def log_search(self, at: float, topic: str, ok: bool) -> None:
        self.conn.execute("INSERT INTO search_log VALUES (?,?,?)", (at, topic, int(ok)))
        self.conn.commit()

    def meta_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row[0] if row else None

    def meta_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
