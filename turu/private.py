"""私密区（architecture.md §7）——一块谁也读不到的地方。

设计承诺：任何检索/导出/日志接口都**永不返回**这里的内容，包括对主人。
它唯一的对外通道是对气质的有界增量——读不到它，但感觉得到它。

落盘时做流加密混淆（密钥存在库内 meta 里）。诚实说明：这防的是
"顺手翻看"（SQLite 浏览器里只见密文），防不了下决心拆解的人——
真正的边界是上面那条接口纪律，而不是密码学。
它不能写事实层；对外的动作（搜索、发言）永远不私密。
"""

import hashlib
import secrets

from .models import new_id


def _keystream(key: bytes, n: int) -> bytes:
    out = b""
    counter = 0
    while len(out) < n:
        out += hashlib.blake2b(
            key + counter.to_bytes(8, "big"), digest_size=32
        ).digest()
        counter += 1
    return out[:n]


class PrivateZone:
    def __init__(self, store):
        self.store = store
        key_hex = store.meta_get("private_key")
        if key_hex is None:
            key_hex = secrets.token_hex(32)
            store.meta_set("private_key", key_hex)
        self._key = bytes.fromhex(key_hex)

    def keep(self, kind: str, content: str, at: float) -> None:
        """写入。没有对应的读取方法——这是有意的。"""
        raw = content.encode("utf-8")
        data = bytes(a ^ b for a, b in zip(raw, _keystream(self._key, len(raw))))
        self.store.private_put(new_id(at), at, kind, data)

    def count(self) -> int:
        """唯一的观察窗口：只有多少，没有是什么。"""
        return self.store.private_count()
