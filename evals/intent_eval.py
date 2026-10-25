"""意图解析评测：用真实大模型跑 evals/intent.yaml，输出准确率、模型调用次数与延迟。

需要环境变量 LLM_BASE_URL、LLM_API_KEY；可用 INTENT_MODEL 指定模型。
用法：uv run python evals/intent_eval.py [模型名...]
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import yaml

from pozhan.case import load_case
from pozhan.engine import Ask, Command, Present
from pozhan.intent import Clarify, Interpreter, LLMClassifier, RuleMatcher
from pozhan.llm import OpenAICompatLLM

ROOT = Path(__file__).resolve().parent.parent


def kind(result) -> str:
    return {Ask: "ask", Present: "present", Clarify: "clarify", Command: "command"}[type(result)]


def as_set(value) -> set:
    return set(value) if isinstance(value, list) else {value}


def correct(item: dict, result) -> bool:
    if kind(result) not in as_set(item["expect"]):
        return False
    if isinstance(result, Present | Clarify):
        if "card" in item and result.card not in as_set(item["card"]):
            return False
        if isinstance(result, Present) and "claim" in item and result.claim not in as_set(item["claim"]):
            return False
    return True


class CountingLLM(OpenAICompatLLM):
    calls = 0

    async def complete(self, model, messages, *, timeout=10.0):
        CountingLLM.calls += 1
        return await super().complete(model, messages, timeout=timeout)


async def run(model: str) -> None:
    case = load_case(ROOT / "cases" / "golden-watch.yaml")
    items = yaml.safe_load((ROOT / "evals" / "intent.yaml").read_text(encoding="utf-8"))
    llm = CountingLLM(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"])
    it = Interpreter(RuleMatcher(), LLMClassifier(llm, model))
    CountingLLM.calls = 0

    async def one(item):
        t0 = time.time()
        result = await it.interpret(item["text"], case)
        return item, result, time.time() - t0

    results = []
    for batch in range(0, len(items), 6):
        results += await asyncio.gather(*(one(i) for i in items[batch : batch + 6]))
    ok = sum(correct(i, r) for i, r, _ in results)
    lat = sorted(dt for _, _, dt in results if dt > 0.05)  # 只统计真正调用了模型的
    p50 = lat[len(lat) // 2] if lat else 0
    rate = f"{ok}/{len(items)} ({ok / len(items):.0%})"
    print(f"\n== {model}  准确 {rate}  模型调用 {CountingLLM.calls} 次  p50 {p50:.2f}s")
    for item, result, _ in results:
        if not correct(item, result):
            print(f"  ✗ {item['text']}  →  {result}")
    await llm.aclose()


if __name__ == "__main__":
    for m in sys.argv[1:] or [os.environ.get("INTENT_MODEL", "deepseek/deepseek-v4-flash")]:
        asyncio.run(run(m))
