from pozhan.director import Director
from pozhan.director.guard import clean, split_sentences, violation
from pozhan.director.narrator import cn, duration
from pozhan.director.suspect import Suspect
from pozhan.engine import (
    AlreadyBroken,
    Answer,
    Briefing,
    Broke,
    Confession,
    Lawyer,
    ReadClaims,
    Remaining,
    Wrong,
    new_game,
)
from pozhan.intent import Clarify
from pozhan.llm import LLMError


class ScriptLLM:
    """按预设的片段流式返回，记录收到的 messages。"""

    def __init__(self, *chunks: str, fail: bool = False) -> None:
        self.chunks = chunks
        self.fail = fail
        self.messages = None

    async def complete(self, model, messages, *, timeout=10.0):
        return "".join(self.chunks)

    async def stream(self, model, messages, *, timeout=20.0):
        self.messages = messages
        if self.fail:
            raise LLMError("boom")
        for c in self.chunks:
            yield c


async def lines(director, case, state, outcome, history=()):
    return [line async for line in director.speak(case, state, outcome, list(history))]


def test_numbers_are_spoken_in_chinese():
    assert [cn(n) for n in (1, 3, 10, 12, 20, 35)] == ["一", "三", "十", "十二", "二十", "三十五"]
    assert duration(14 * 60) == "十四分钟"
    assert duration(75) == "一分十五秒"


def test_split_sentences_keeps_trailing_fragment():
    assert split_sentences("你好。我没去！真的？？还有") == (["你好。", "我没去！", "真的？？"], "还有")
    assert split_sentences("是我……拿的。") == (["是我……拿的。"], "")


async def test_confession_split_across_sentences_is_still_caught(case):
    d = Director(llm=ScriptLLM("好吧好吧。", "表是我拿走的。"), model="m")
    out = await lines(d, case, new_game(case, 0), Answer("说实话"))
    assert "".join(line.text for line in out) == "好吧好吧。"


def test_clean_strips_actions_markdown_and_emoji():
    assert clean("（擦汗）我、我没去😅**真的**") == "我、我没去真的"


def test_guard_blocks_confession_and_breaking_character():
    assert violation("好吧，是我拿的。", may_confess=False) == "premature-confession"
    assert violation("好吧，是我拿的。", may_confess=True) is None
    assert violation("作为一个AI，我不能回答。", may_confess=False) == "out-of-character"
    assert violation("我一直在包厢唱歌。", may_confess=False) is None
    assert violation("好吧，我承认我上过十八楼。", may_confess=False) is None
    assert violation("是我，拿的。", may_confess=False) == "premature-confession"


async def test_briefing_is_deterministic_and_reads_claims_verbatim(case):
    d = Director(llm=None, model="")
    out = await lines(d, case, new_game(case, 0), Briefing())
    assert [line.speaker for line in out] == ["narrator", "suspect", "narrator"]
    for claim in case.claims:
        assert claim.text in out[1].text


def test_emoji_follows_suspect_stage_or_stays_neutral(case):
    d = Director(llm=None, model="")
    state = new_game(case, 0)
    assert d.emoji(case, state, Answer("q")) == "😌"
    assert d.emoji(case, state, ReadClaims()) == "😶"
    raised = state.__class__(case_id=case.id, started_at=0, stage=2)
    assert d.emoji(case, raised, Broke(case.contradictions[1], 2)) == "😲"


async def test_broke_prompts_the_concession_then_narrates(case):
    llm = ScriptLLM("我……我是上去过，", "可那是拿奖品！")
    d = Director(llm=llm, model="m")
    x = case.contradiction(2, 1)
    state = new_game(case, 0).__class__(case_id=case.id, started_at=0, stage=1, broken=(1,))
    out = await lines(d, case, state, Broke(x, 1))
    assert out[0].speaker == "narrator" and out[0].text == "证词一被戳破了！"  # 判定先说，零延迟
    assert "".join(line.text for line in out[1:-1]) == "我……我是上去过，可那是拿奖品！"
    assert out[-1].text == "他还在坚持证词二、证词三。"
    task = llm.messages[-1]["content"]
    assert "电梯监控截图" in task and x.concession in task
    assert x.concession in llm.messages[0]["content"]  # 已承认的让步写进人设，保证后续不反悔


async def test_slip_hint_reaches_the_prompt(case):
    llm = ScriptLLM("十八楼那会儿走廊灯都关了。")
    d = Director(llm=llm, model="m")
    slip = case.contradiction(2, 1)
    await lines(d, case, new_game(case, 0), Answer("你几点回的包厢", slip=slip))
    assert slip.slip in llm.messages[-1]["content"]


async def test_premature_confession_is_replaced_by_fallback(case):
    d = Director(llm=ScriptLLM("好吧，是我拿的。", "我欠了钱。"), model="m")
    out = await lines(d, case, new_game(case, 0), Answer("你认不认罪"))
    assert len(out) == 1 and "是我拿的" not in out[0].text


async def test_confession_may_confess(case):
    d = Director(llm=ScriptLLM("是我拿的……我欠了钱。"), model="m")
    out = await lines(d, case, new_game(case, 0), Confession(case.contradiction(4, 3)))
    assert out[0].text == "证词三被戳破了！"
    assert "".join(line.text for line in out if line.speaker == "suspect") == "是我拿的……我欠了钱。"
    assert "案件告破" in out[-1].text


async def test_model_failure_falls_back(case):
    d = Director(llm=ScriptLLM(fail=True), model="m")
    out = await lines(d, case, new_game(case, 0), Answer("你在哪"))
    assert len(out) == 1 and out[0].speaker == "suspect" and out[0].text


async def test_overlong_reply_is_cut_at_a_sentence(case):
    d = Director(llm=ScriptLLM("我在包厢。" * 40), model="m")
    out = await lines(d, case, new_game(case, 0), Answer("你在哪"))
    assert sum(len(line.text) for line in out) <= 90


async def test_narrator_only_outcomes(case):
    d = Director(llm=None, model="")
    s = new_game(case, 0)
    assert "已经被戳破" in (await lines(d, case, s, AlreadyBroken(1)))[0].text
    assert "律师" in (await lines(d, case, s, Lawyer("strikes")))[0].text
    assert case.reveal in (await lines(d, case, s, Lawyer("timeout")))[0].text
    assert "十四分钟" in (await lines(d, case, s, Remaining(2, 14 * 60)))[0].text
    assert "几号卡" in (await lines(d, case, s, Clarify(None, 1)))[0].text


async def test_wrong_presentation_has_rebuttal_and_countdown(case):
    d = Director(llm=ScriptLLM("我去洗手间了不行吗？"), model="m")
    out = await lines(d, case, new_game(case, 0), Wrong(card=1, claim=1, strikes_left=2))
    assert [line.text for line in out] == [
        "这张卡驳不倒证词一。",
        "我去洗手间了不行吗？",
        "律师还有二次就到。",
    ]


def test_suspect_history_window():
    from pozhan.director.suspect import _recent

    history = [{"role": "system", "content": "x"}] + [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(30)
    ]
    assert len(_recent(history)) == 12 and _recent(history)[-1]["content"] == "29"
    assert Suspect(ScriptLLM(), "m").model == "m"
