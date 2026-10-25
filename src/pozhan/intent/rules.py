"""规则匹配：编号句式和指令。命中就不调用大模型，零延迟（#4 风险 R1）。"""

import re

from pozhan.case.model import Case
from pozhan.engine.events import Command, CommandKind, Event, Present

_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
NUM = r"(\d+|[一二两三四五六七八九十]+)"


def to_int(token: str) -> int | None:
    """「3」「三」「十二」→ 整数；无法识别返回 None。"""
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if "十" in token:
        tens, _, ones = token.partition("十")
        t = _DIGITS.get(tens, 1) if tens else 1
        o = _DIGITS.get(ones, 0) if ones else 0
        return t * 10 + o
    if len(token) == 1:
        return _DIGITS.get(token)
    return None


_CARD = re.compile(rf"(?:第\s*)?{NUM}\s*(?:号|张)\s*(?:线索)?卡|卡(?:片)?\s*{NUM}\s*号?")
_CLAIM = re.compile(rf"证词\s*{NUM}|(?:第\s*)?{NUM}\s*(?:号|条)\s*(?:证词)?")


def _first_num(pattern: re.Pattern[str], text: str) -> tuple[int | None, tuple[int, int] | None]:
    m = pattern.search(text)
    if not m:
        return None, None
    token = next(g for g in m.groups() if g)
    return to_int(token), m.span()


def _strip_card(text: str) -> tuple[int | None, str]:
    card, span = _first_num(_CARD, text)
    if span is None:
        return None, text
    return card, text[: span[0]] + " " + text[span[1] :]


_COMMANDS: list[tuple[CommandKind, re.Pattern[str]]] = [
    (CommandKind.NEXT_CASE, re.compile(r"(?:下一个|下个|换个|换一个|新的?|别的)案子|换(?:个|一个)案件")),
    (CommandKind.LIST_CASES, re.compile(r"(?:有|还有)(?:哪些|什么|几个)案子|案子(?:列表|有哪些)")),
    (CommandKind.RESTART, re.compile(r"重新开始|再来一局|重开一局|再玩一局")),
    (CommandKind.QUIT, re.compile(r"结束游戏|退出游戏|不玩了|游戏结束吧")),
    (CommandKind.START, re.compile(r"^(?:开始审讯|开始游戏|开始吧|开一局)")),
    (CommandKind.REPEAT, re.compile(r"再说一遍|再说一次|没听清|重复一遍|重复一下|刚才说什么")),
    (
        CommandKind.REMAINING,
        re.compile(r"(?:还|剩)(?:有|下|剩)?(?:几次|多少次|几回)|还有多(?:久|少时间)|剩(?:多少|几分钟)"),
    ),
    (CommandKind.RULES, re.compile(r"游戏规则|规则是什么|规则是啥|怎么玩|玩法")),
]
_READ = re.compile(r"念|读一下|读读|再听|是什么|有哪些|写的什么|写了什么")


def match(text: str, case: Case) -> Event | None:
    """规则匹配；无法确定时返回 None，交给大模型。"""
    t = text.strip().rstrip("。！？!?.，, ")

    for kind, pattern in _COMMANDS:
        if pattern.search(t):
            return Command(kind)

    card, rest = _strip_card(t)
    claim, _ = _first_num(_CLAIM, rest)
    if _READ.search(t):
        if "证词" in t and card is None:
            return Command(CommandKind.READ_CLAIMS)
        if card is not None and claim is None:
            return Command(CommandKind.READ_CARD, card=card)

    if card is not None and claim is not None:
        return Present(card=card, claim=claim, text=text)
    return None


class RuleMatcher:
    def match(self, text: str, case: Case) -> Event | None:
        return match(text, case)
