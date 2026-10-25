"""玩家这一轮做了什么。由 intent 模块从原话解析得到。"""

from dataclasses import dataclass
from enum import StrEnum


class CommandKind(StrEnum):
    START = "start"  # 开局
    RESTART = "restart"  # 重新开始
    READ_CLAIMS = "read_claims"  # 念一下证词
    READ_CARD = "read_card"  # 念一下 N 号卡
    REMAINING = "remaining"  # 还有几次机会
    RULES = "rules"  # 规则是什么
    REPEAT = "repeat"  # 再说一遍
    QUIT = "quit"  # 结束游戏


@dataclass(frozen=True)
class Ask:
    """普通提问或闲聊，交给嫌疑人回答。topic 是问到的隐藏证词（案件里的编号），由意图解析给出（#46）。"""

    text: str
    topic: int | None = None


@dataclass(frozen=True)
class Present:
    """出示 card 号卡，反驳玩家口中的第 claim 条证词（按说出口的顺序，#46）。"""

    card: int
    claim: int
    text: str = ""


@dataclass(frozen=True)
class Command:
    kind: CommandKind
    card: int | None = None  # 仅 READ_CARD 使用


Event = Ask | Present | Command
