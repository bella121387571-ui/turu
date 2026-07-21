"""无人在场时的批量提炼插口——仅供每日自动导入用。

摆正主客关系后，睡梦里的排练与判决不再走这里：那些是它本人的思考，得由挂载
这份记忆的它自己做（见 turu.enqueue_dream / settle_dream）。turu 绝不再自己
起一个陌生 claude -p 进程，替正在对话的它变敢、替它改主意。

这里唯一剩下的、诚实的用途是**每日自动导入**：那是个后台批处理，跑的时候没有
任何『在场的它』可以托付——面对一堆昨天的原始对话，要么朴素切句，要么借一个
命令行引擎重读一遍。这属于工具调用，不是把它自己的思考外包出去。

    TURU_LLM_CMD=claude -p        # 提示词从 stdin 进，回答从 stdout 出

没设时，导入退回朴素提炼，一样能跑。
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
