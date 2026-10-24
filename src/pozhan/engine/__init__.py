"""审讯规则：纯函数式状态机。

输赢、升档、认罪都只在这里决定，不调用大模型（Proposal #3 决策 2/3）。
"""

from pozhan.engine.events import Ask, Command, CommandKind, Event, Present
from pozhan.engine.outcomes import (
    AlreadyBroken,
    Answer,
    Briefing,
    Broke,
    Confession,
    GameOver,
    Lawyer,
    Outcome,
    Quit,
    ReadCard,
    ReadClaims,
    Remaining,
    Rules,
    UnknownRef,
    Wrong,
)
from pozhan.engine.rules import apply, new_game
from pozhan.engine.state import Interrogation, Phase

__all__ = [
    "AlreadyBroken",
    "Answer",
    "Ask",
    "Briefing",
    "Broke",
    "Command",
    "CommandKind",
    "Confession",
    "Event",
    "GameOver",
    "Interrogation",
    "Lawyer",
    "Outcome",
    "Phase",
    "Present",
    "Quit",
    "ReadCard",
    "ReadClaims",
    "Remaining",
    "Rules",
    "UnknownRef",
    "Wrong",
    "apply",
    "new_game",
]
