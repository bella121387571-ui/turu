"""向量化，可插拔。

M0 默认用零依赖的字符 n-gram 哈希向量：不需要 API key、不需要模型，
中英文都能算出够用的粗粒度相似度，让模拟器在任何机器上直接跑。
将来接真 embedding API 时，实现同样的 Embedder 协议换进来即可，
数据库里的向量维度不同会自动重算。
"""

import hashlib
import math
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashEmbedder:
    """字符 1~3-gram 特征哈希 + L2 归一化。"""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        text = text.strip().lower()
        for n in (1, 2, 3):
            for i in range(len(text) - n + 1):
                gram = text[i : i + n]
                h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big")
                idx = h % self.dim
                sign = 1.0 if (h >> 63) & 1 else -1.0
                # 长 gram 更有辨识度，权重更高
                vec[idx] += sign * n
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _grams(text: str, ns: tuple[int, ...] = (1, 2, 3)) -> set[str]:
    text = "".join(text.split()).lower()
    out: set[str] = set()
    for n in ns:
        for i in range(len(text) - n + 1):
            out.add(text[i : i + n])
    return out


def gram_containment(query: str, doc: str) -> float:
    """查询的字符 n-gram 有多少比例出现在文档里。

    余弦对"短查询 vs 长句子"天然偏低（长句稀释），containment 是不对称的
    词法信号，专门补这一块。检索相似度 = max(cosine, containment)。
    """
    q = _grams(query)
    if not q:
        return 0.0
    return len(q & _grams(doc)) / len(q)
