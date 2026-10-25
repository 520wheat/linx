"""规则引擎对一个事件给出的结果。director 只根据这里的结果决定说什么。"""

from dataclasses import dataclass
from typing import Literal

from pozhan.case.model import Contradiction


@dataclass(frozen=True)
class Briefing:
    """开局：介绍案情、嫌疑人开场陈述证词、讲规则。"""


@dataclass(frozen=True)
class Answer:
    """嫌疑人回答提问。slip 不为空时，这句话要露出指向该矛盾的破绽。"""

    question: str
    slip: Contradiction | None = None


@dataclass(frozen=True)
class Broke:
    """戳破了一条证词，嫌疑人升到 stage 档。revealed 是随让步改口说出的新证词（#46）。"""

    contradiction: Contradiction
    stage: int
    revealed: tuple[int, ...] = ()


@dataclass(frozen=True)
class Revealed:
    """侦探问到了隐藏证词的话题，嫌疑人说出这条新证词（#46）。blurted：玩家卡住了，他自己说漏的（#53）。"""

    claim: int
    blurted: bool = False


@dataclass(frozen=True)
class Confession:
    """最后一条证词被戳破，嫌疑人崩溃认罪。"""

    contradiction: Contradiction


@dataclass(frozen=True)
class AlreadyBroken:
    """出示的证词早已戳破，不扣机会。"""

    claim: int


@dataclass(frozen=True)
class Wrong:
    """出示没有驳倒证词，错误次数 +1。"""

    card: int
    claim: int
    strikes_left: int


@dataclass(frozen=True)
class Weak:
    """出示的是间接证据：沾边但驳不倒，不扣机会（#49）。claim 是案件里的证词编号。"""

    card: int
    claim: int
    reason: str


@dataclass(frozen=True)
class UnknownRef:
    """提到了不存在的卡，或还没说出口的证词序号，不扣机会。claim 是玩家说的序号。"""

    card: int | None
    claim: int | None


@dataclass(frozen=True)
class Lawyer:
    """律师到场，游戏失败。"""

    reason: Literal["strikes", "timeout"]


@dataclass(frozen=True)
class ReadClaims:
    pass


@dataclass(frozen=True)
class ReadCard:
    card: int


@dataclass(frozen=True)
class Remaining:
    strikes_left: int
    seconds_left: int


@dataclass(frozen=True)
class Rules:
    pass


@dataclass(frozen=True)
class Repeat:
    """「再说一遍」：由 game 原样复述上一轮回复，不经过大模型。"""


@dataclass(frozen=True)
class Quit:
    pass


@dataclass(frozen=True)
class CaseList:
    """念案件库里的案子（#53）。current 是正在玩的案子在列表里的下标。"""

    titles: tuple[str, ...]
    current: int


@dataclass(frozen=True)
class GameOver:
    """游戏已结束后又有输入：提示可以重新开始。"""


Outcome = (
    Briefing
    | Answer
    | Broke
    | Revealed
    | Confession
    | AlreadyBroken
    | Wrong
    | Weak
    | UnknownRef
    | Lawyer
    | ReadClaims
    | ReadCard
    | Remaining
    | Rules
    | Repeat
    | Quit
    | CaseList
    | GameOver
)
