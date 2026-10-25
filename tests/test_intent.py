import pytest

from pozhan.engine import Ask, Command, CommandKind, Present
from pozhan.intent import Clarify, Interpreter, LLMClassifier, RuleMatcher
from pozhan.intent.classifier import parse_reply
from pozhan.intent.rules import match, to_int
from pozhan.llm import LLMError


@pytest.mark.parametrize(
    ("token", "value"),
    [("3", 3), ("三", 3), ("两", 2), ("十", 10), ("十二", 12), ("二十", 20), ("二十一", 21), ("x", None)],
)
def test_chinese_numbers(token, value):
    assert to_int(token) == value


@pytest.mark.parametrize(
    ("text", "card", "claim"),
    [
        ("用2号卡反驳证词1", 2, 1),
        ("用二号卡反驳证词一", 2, 1),
        ("第二张卡，第三条证词", 2, 3),
        ("四号卡，反驳第一条", 4, 1),
        ("出示3号卡，反驳第2条证词。", 3, 2),
        ("证词3，用4号卡", 4, 3),
        ("卡2反驳1号证词", 2, 1),
    ],
)
def test_numbered_presentations(case, text, card, claim):
    assert match(text, case) == Present(card=card, claim=claim, text=text)


@pytest.mark.parametrize(
    ("text", "kind", "card"),
    [
        ("念一下证词", CommandKind.READ_CLAIMS, None),
        ("你的证词是什么来着", CommandKind.READ_CLAIMS, None),
        ("念一下3号卡", CommandKind.READ_CARD, 3),
        ("二号卡写的什么", CommandKind.READ_CARD, 2),
        ("还有几次机会", CommandKind.REMAINING, None),
        ("还剩多少时间", CommandKind.REMAINING, None),
        ("游戏规则是什么", CommandKind.RULES, None),
        ("再说一遍", CommandKind.REPEAT, None),
        ("没听清", CommandKind.REPEAT, None),
        ("结束游戏", CommandKind.QUIT, None),
        ("重新开始", CommandKind.RESTART, None),
        ("开始审讯", CommandKind.START, None),
    ],
)
def test_commands(case, text, kind, card):
    assert match(text, case) == Command(kind, card=card)


@pytest.mark.parametrize(
    "text",
    [
        "你九点到十点在哪里？",
        "电梯监控拍到你九点半上了18楼",  # 没报编号：交给大模型
        "出示2号卡",  # 只有卡没有证词：交给大模型推断
        "我们有GPS记录",
        "你说一下，你昨晚干嘛了",
    ],
)
def test_falls_through_to_model(case, text):
    assert match(text, case) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '{"present": true, "card": "2", "claim": "1号", "confidence": 0.9}',
            Present(2, 1, "t", explicit=False),
        ),
        ('```json\n{"present": true, "card": 4, "claim": 3}\n```', Present(4, 3, "t", explicit=False)),
        ('{"present": false, "card": null, "claim": null}', Ask("t")),
        ('{"present": true, "card": 2, "claim": null, "confidence": 0.9}', (2, None)),
        ('{"present": true, "card": 2, "claim": 1, "confidence": 0.3}', (2, 1)),
        ("我不知道", Ask("t")),
        ("{broken json", Ask("t")),
    ],
)
def test_parse_reply(raw, expected):
    assert parse_reply(raw, "t") == expected


class FakeLLM:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls = 0

    async def complete(self, model, messages, *, timeout=10.0):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    async def stream(self, model, messages, *, timeout=20.0):
        yield ""


async def test_rule_hits_never_call_the_model(case):
    llm = FakeLLM('{"present": false}')
    it = Interpreter(RuleMatcher(), LLMClassifier(llm, "m"))
    assert await it.interpret("2号卡反驳证词1", case) == Present(2, 1, "2号卡反驳证词1")
    assert await it.interpret("念一下证词", case) == Command(CommandKind.READ_CLAIMS)
    assert llm.calls == 0


async def test_model_presentation_and_clarify(case):
    it = Interpreter(RuleMatcher(), LLMClassifier(FakeLLM('{"present": true, "card": 2, "claim": 1}'), "m"))
    # 只是陈述卡的内容，没说「出示」「用……卡」：算顺口提到（#49）
    text = "电梯监控拍到你上了18楼"
    assert await it.interpret(text, case) == Present(2, 1, text, explicit=False)
    it = Interpreter(
        RuleMatcher(), LLMClassifier(FakeLLM('{"present": true, "card": null, "claim": null}'), "m")
    )
    assert await it.interpret("看这张卡", case) == Clarify(None, None)


async def test_model_failure_degrades_to_question(case):
    it = Interpreter(RuleMatcher(), LLMClassifier(FakeLLM(LLMError("timeout")), "m"))
    assert await it.interpret("你到底去没去十八楼", case) == Ask("你到底去没去十八楼")


@pytest.mark.parametrize(
    ("text", "explicit"),
    [
        ("出示便利贴照片", True),
        ("用指纹报告反驳他", True),
        ("看这张，电梯监控拍到你了", True),
        ("拿出电梯截图", True),
        ("九点二十到九点五十没人点歌，你那半小时在干嘛？", False),
        ("表盒上为什么有你的指纹", False),
    ],
)
def test_explicit_presentation_wording(text, explicit):
    assert parse_reply('{"present": true, "card": 2, "claim": 1}', text).explicit is explicit
