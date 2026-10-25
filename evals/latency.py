"""延迟评测：比较不同模型在「嫌疑人回答」和「意图分类」两种请求上的首字延迟与总耗时。

需要环境变量 LLM_BASE_URL、LLM_API_KEY。
用法：uv run python evals/latency.py 模型1 模型2 ...
"""

import asyncio
import os
import sys
import time
from pathlib import Path

from pozhan.case import load_case
from pozhan.config import Settings
from pozhan.director.suspect import _system, task_answer
from pozhan.engine import new_game
from pozhan.intent.classifier import build_messages
from pozhan.llm import OpenAICompatLLM

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ["你九点到十点在干嘛？", "你最近手头紧吗？", "你认识老板多久了？", "你在包厢唱了什么歌？"]


async def ttft(llm, model, messages):
    t0 = time.monotonic()
    first = None
    async for _ in llm.stream(model, messages, timeout=30):
        first = first or time.monotonic() - t0
    return first, time.monotonic() - t0


async def bench(model: str) -> None:
    case = load_case(ROOT / "cases" / "golden-watch.yaml")
    state = new_game(case, 0)
    llm = OpenAICompatLLM(
        os.environ["LLM_BASE_URL"],
        os.environ["LLM_API_KEY"],
        temperature=0.8,
        extra_body=Settings.from_env().llm_extra_body,
    )
    suspect, intent = [], []
    for q in QUESTIONS:
        msgs = [
            {"role": "system", "content": _system(case, state, 0)},
            {"role": "user", "content": f"【本轮任务，不要复述】{task_answer(q, None)}"},
        ]
        try:
            suspect.append(await ttft(llm, model, msgs))
            intent.append(await ttft(llm, model, build_messages(case, q)))
        except Exception as e:
            print(f"{model}: {e!r}")
            return
    med = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
    print(
        f"{model:45s} 嫌疑人 首字 {med([a for a, _ in suspect]):.2f}s 总 {med([b for _, b in suspect]):.2f}s"
        f" | 意图 首字 {med([a for a, _ in intent]):.2f}s 总 {med([b for _, b in intent]):.2f}s"
    )
    await llm.aclose()


async def main(models):
    await asyncio.gather(*(bench(m) for m in models))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
