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
    assert reply == "😌这个嘛……我一直在包厢。"  # 先说语气词（#50）
    assert llm.streams == 1  # 只生成了一次回答
    assert elapsed < 0.5  # 分类和生成并行：约 0.3s，而不是串行的 0.6s


async def test_presentation_discards_the_speculative_answer(case):
    llm = SlowLLM('{"present": true, "card": 2, "claim": 1}')
    game = make_game(case, llm)
    await say(game, "开始")
    reply, _ = await say(game, "电梯监控拍到你上了十八楼")
    assert reply.startswith("😠证词一被戳破了！")
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


async def test_history_keeps_only_the_suspects_own_words(case):
    # 旁白混进历史，大模型会学着说「证词一被戳破了」（#46）
    game = make_game(case, SlowLLM('{"present": false}'))
    await say(game, "开始")
    await say(game, "用2号卡反驳证词1")
    await say(game, "念一下证词")
    assistant = [m["content"] for m in game.store.get("k").history if m["role"] == "assistant"]
    assert assistant[1] == "我一直在包厢。"
    assert assistant[2] == "……"
    assert not any("被戳破" in a for a in assistant[1:])


async def test_likely_question_gets_emotion_and_filler_before_classification(case):
    # 分类要 0.3 秒；看起来是提问的话，情绪和语气词立刻发出（#50）
    llm = SlowLLM('{"present": false}')
    game = make_game(case, llm)
    await say(game, "开始")
    t0 = time.monotonic()
    chunks = []
    async for part in game.turn("k", "你九点半在哪？"):
        chunks.append((part, time.monotonic() - t0))
    assert [p for p, _ in chunks[:2]] == ["😌", "这个嘛……"]
    assert chunks[1][1] < 0.1
    assert "".join(p for p, _ in chunks) == "😌这个嘛……我一直在包厢。"
    history = game.store.get("k").history
    assert history[-1]["content"] == "这个嘛……我一直在包厢。"


async def test_presentations_get_no_filler(case):
    game = make_game(case, SlowLLM('{"present": false}'))
    await say(game, "开始")
    reply, _ = await say(game, "用2号卡反驳证词1")
    assert reply.startswith("😠证词一被戳破了！")


async def test_next_case_switches_and_lists_cases(case):
    from dataclasses import replace

    from pozhan.engine import CommandKind
    from pozhan.intent.rules import match

    other = replace(case, id="other", title="另一个案子")
    game = Game(
        case=case,
        cases=(case, other),
        interpreter=Interpreter(RuleMatcher(), None),
        director=Director(None, ""),
        store=MemoryStore(),
    )
    assert match("换个案子", case).kind is CommandKind.NEXT_CASE
    assert match("有哪些案子", case).kind is CommandKind.LIST_CASES
    await say(game, "开始审讯")
    assert game.case_of(game.store.get("k")).id == case.id
    listing, _ = await say(game, "有哪些案子")
    assert "一，年会夜的金表；二，另一个案子" in listing and "第一个" in listing
    await say(game, "用2号卡反驳证词1")
    reply, _ = await say(game, "下一个案子")
    session = game.store.get("k")
    assert session.case_id == "other" and session.state.broken == () and reply.startswith("😌")
    await say(game, "重新开始")
    assert game.case_of(session).id == "other"  # 重新开始重玩当前这个
    await say(game, "下一个案子")
    assert game.case_of(session).id == case.id  # 最后一个之后回到第一个


async def test_listing_cases_before_starting_does_not_start_a_game(case):
    from dataclasses import replace

    other = replace(case, id="other", title="另一个案子")
    game = Game(
        case=case,
        cases=(case, other),
        interpreter=Interpreter(RuleMatcher(), None),
        director=Director(None, ""),
        store=MemoryStore(),
    )
    listing, _ = await say(game, "有哪些案子")
    assert "两个案子" in listing and game.store.get("k").state is None
    reply, _ = await say(game, "换个案子")  # 第一句就换：直接开第二个
    assert game.store.get("k").case_id == "other" and reply.startswith("😌")
