from collections.abc import AsyncIterator
from dataclasses import dataclass

from pozhan.case.model import Case
from pozhan.director import narrator
from pozhan.director.suspect import Suspect, fallback, task_answer, task_broke, task_confess, task_wrong
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
from pozhan.engine.state import Interrogation
from pozhan.intent.interpreter import Clarify
from pozhan.llm.client import LLM, Message

NEUTRAL = "😶"  # 只有旁白说话的回合用中性情绪

# 这些结果里嫌疑人会开口，本轮情绪取嫌疑人当前档位
_SUSPECT_SPEAKS = (Briefing, Answer, Broke, Confession, Wrong)


@dataclass(frozen=True)
class Line:
    """一轮回复里的一段话。speaker 为 narrator（旁白）或 suspect（嫌疑人）。"""

    speaker: str
    text: str


class Director:
    def __init__(self, llm: LLM | None, model: str) -> None:
        self.suspect = Suspect(llm, model) if llm is not None else None

    def emoji(self, case: Case, state: Interrogation, outcome: Outcome | Clarify) -> str:
        """灵矽只取回复的第一个 emoji 决定整轮情绪，所以一轮只能有一种情绪。"""
        if isinstance(outcome, _SUSPECT_SPEAKS):
            return case.stages[min(state.stage, len(case.stages) - 1)].emoji
        return NEUTRAL

    async def _suspect(
        self,
        case: Case,
        state: Interrogation,
        task: str,
        history: list[Message],
        may_confess: bool = False,
    ) -> AsyncIterator[Line]:
        if self.suspect is None:  # 未配置大模型（本地开发）：用兜底台词
            yield Line("suspect", fallback(case, state.stage))
            return
        async for s in self.suspect.say(case, state, task, history, may_confess=may_confess):
            yield Line("suspect", s)

    async def speak(
        self,
        case: Case,
        state: Interrogation,
        outcome: Outcome | Clarify,
        history: list[Message],
    ) -> AsyncIterator[Line]:
        def say(text: str) -> Line:
            return Line("narrator", text)

        match outcome:
            case Briefing():
                yield say(narrator.briefing(case))
                yield Line("suspect", narrator.opening_statement(case))
                yield say(narrator.rules(case))
            case Answer(question=q, slip=slip):
                async for line in self._suspect(case, state, task_answer(q, slip), history):
                    yield line
            case Broke(contradiction=x):
                async for line in self._suspect(case, state, task_broke(case, x), history):
                    yield line
                yield say(narrator.broke(case, state, x.claim))
            case Confession(contradiction=x):
                async for line in self._suspect(
                    case, state, task_confess(case, x), history, may_confess=True
                ):
                    yield line
                yield say(narrator.confession_wrap(case))
            case Wrong(card=card, claim=claim, strikes_left=left):
                async for line in self._suspect(case, state, task_wrong(case, card, claim), history):
                    yield line
                yield say(narrator.wrong(case, claim, left))
            case AlreadyBroken(claim=claim):
                yield say(narrator.already_broken(claim))
            case UnknownRef(card=card, claim=claim):
                yield say(narrator.unknown_ref(case, card, claim))
            case Clarify(card=card, claim=claim):
                yield say(narrator.clarify(card, claim))
            case Lawyer(reason=reason):
                yield say(narrator.lawyer(case, reason))
            case ReadClaims():
                yield say(narrator.read_claims(case, state))
            case ReadCard(card=card):
                yield say(narrator.read_card(case, card))
            case Remaining(strikes_left=left, seconds_left=seconds):
                yield say(narrator.remaining(left, seconds))
            case Rules():
                yield say(narrator.rules(case))
            case Quit():
                yield say(narrator.quit_game(case))
            case GameOver():
                yield say(narrator.game_over())
