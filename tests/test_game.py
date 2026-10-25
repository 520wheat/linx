"""编排层测试：投机生成（#22）。"""

import asyncio
import time

from pozhan.director import Director
from pozhan.game import Game
from pozhan.intent import Interpreter, LLMClassifier, RuleMatcher
from pozhan.session import MemoryStore


class SlowLLM:
    """complete 用于意图分类，stream 用于嫌疑人台词；都人为延迟 0.3 秒。"""

    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.streams = 0
        self.cancelled = 0

    async def complete(self, model, messages, *, timeout=10.0):
        await asyncio.sleep(0.3)
        return self.verdict

    async def stream(self, model, messages, *, timeout=20.0):
        self.streams += 1
        try:
            await asyncio.sleep(0.3)
            yield "我一直在包厢。"
        except asyncio.CancelledError:
            self.cancelled += 1
            raise


def make_game(case, llm):
    return Game(
        case=case,
        interpreter=Interpreter(RuleMatcher(), LLMClassifier(llm, "intent")),
        director=Director(llm, "suspect"),
        store=MemoryStore(),
    )


async def say(game, text):
    t0 = time.monotonic()
    out = "".join([p async for p in game.turn("k", text)])
    return out, time.monotonic() - t0


async def test_question_reuses_the_speculative_answer(case):
    llm = SlowLLM('{"present": false}')
    game = make_game(case, llm)
    await say(game, "开始")
    reply, elapsed = await say(game, "你那天晚上干嘛去了")
    assert reply == "😌我一直在包厢。"
    assert llm.streams == 1  # 只生成了一次回答
    assert elapsed < 0.5  # 分类和生成并行：约 0.3s，而不是串行的 0.6s


async def test_presentation_discards_the_speculative_answer(case):
    llm = SlowLLM('{"present": true, "card": 2, "claim": 1}')
    game = make_game(case, llm)
    await say(game, "开始")
    reply, _ = await say(game, "电梯监控拍到你上了十八楼")
    assert reply.startswith("😏证词一被戳破了！")
    assert llm.cancelled == 1  # 投机生成的「提问回答」被取消
    assert game.store.get("k").state.broken == (1,)


async def test_rule_hits_do_not_speculate(case):
    llm = SlowLLM('{"present": false}')
    game = make_game(case, llm)
    await say(game, "开始")
    await say(game, "念一下证词")
    assert llm.streams == 0


async def test_empty_recognition_does_not_advance_or_call_the_model(case):
    llm = SlowLLM('{"present": false}')
    game = make_game(case, llm)
    await say(game, "开始")
    before = game.store.get("k").state
    reply, _ = await say(game, "  。")
    assert reply == "😶刚才没听清，能再说一遍吗？"
    assert game.store.get("k").state == before and llm.streams == 0


async def test_interrupted_turn_cancels_speculation_and_frees_the_session(case):
    llm = SlowLLM('{"present": false}')
    game = make_game(case, llm)
    await say(game, "开始")
    gen = game.turn("k", "你那天晚上干嘛去了")
    assert await gen.__anext__() == "😌"  # 平台收到情绪 emoji 后，玩家打断了
    await gen.aclose()
    await asyncio.sleep(0.01)
    assert not game.store.get("k").lock.locked()
    assert llm.cancelled == 1  # 后台的投机生成被取消，没有残留任务
    reply, _ = await say(game, "念一下证词")  # 下一轮照常处理
    assert reply.startswith("😶证词一")
