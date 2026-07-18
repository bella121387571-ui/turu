"""夜间 LLM 插口——排练梦与矛盾判决的引擎。

零依赖：环境变量 TURU_LLM_CMD 指定一个命令行，提示词从 stdin 喂进去，
回答从 stdout 读出来。装了 Claude Code 的机器直接填：

    TURU_LLM_CMD=claude -p

没设插口时，用到 LLM 的睡梦阶段会诚实跳过并记入睡眠报告。
"""

import os
import subprocess


def llm_from_env():
    """返回一个 prompt -> str|None 的调用器；没配置则返回 None。"""
    cmd = os.environ.get("TURU_LLM_CMD")
    if not cmd:
        return None

    def call(prompt: str) -> str | None:
        try:
            out = subprocess.run(
                cmd, shell=True, input=prompt,
                capture_output=True, text=True, timeout=180,
            )
            answer = out.stdout.strip()
            return answer or None
        except Exception:
            return None

    return call
