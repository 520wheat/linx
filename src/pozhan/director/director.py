from collections.abc import AsyncIterator
from dataclasses import dataclass

from pozhan.case.model import Case
from pozhan.director import narrator
from pozhan.director.suspect import (
    Suspect,
    fallback,
    task_answer,
    task_broke,
    task_confess,
    task_weak,
    task_wrong,
)
from pozhan.engine.outcomes import (
    AlreadyBroken,
    Answer,
    Briefing,
    Broke,
    CaseList,
    Confession,
    GameOver,
    Hint,
    Lawyer,
    Outcome,
    Quit,
    ReadCard,
    ReadClaims,
    Remaining,
    Revealed,
    Rules,
    Truth,
    UnknownRef,
    Weak,
    Wrong,
)
from pozhan.engine.rules import rating
from pozhan.engine.state import Interrogation
from pozhan.intent.interpreter import Clarify
from pozhan.llm.client import LLM, Message

NEUTRAL = "😶"  # 只有旁白说话的回合用中性情绪

# 嫌疑人开口前的语气词，按档位的情绪选（#50）：零延迟先发出去，灵矽马上就能开始合成，
# 大模型的回答随后接上。同一局里轮换，不连着重复
FILLERS = {
    "😌": ("嗯……", "这个嘛……", "警官……"),
    "😠": ("哼！", "又来了！", "我说，"),
    "😲": ("我、我……", "这……", "那个……"),
    "😭": ("呜……",),
}

# 这些结果里嫌疑人会开口，本轮情绪取嫌疑人当前档位
_SUSPECT_SPEAKS = (Briefing, Answer, Broke, Confession, Wrong, Revealed, Weak)


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

    def filler(self, case: Case, state: Interrogation, turn: int) -> str:
        options = FILLERS.get(case.stages[min(state.stage, len(case.stages) - 1)].emoji, ("嗯，",))
        return options[turn % len(options)]

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
                yield say(narrator.quick_rules())
            case Answer(question=q, slip=slip):
                async for line in self._suspect(case, state, task_answer(q, slip), history):
                    yield line
            case Revealed(claim=claim_id, blurted=blurted):
                # 新证词逐字说出，不经大模型：屏幕上记下的和玩家听到的必须一致（#46）
                yield Line("suspect", case.claim(claim_id).text)
                label = state.label(claim_id)
                yield say(narrator.blurted(label) if blurted else narrator.new_claim(label))
            case Broke(contradiction=x, revealed=amended):
                yield say(narrator.broke(state.label(x.claim)))
                async for line in self._suspect(case, state, task_broke(case, x), history):
                    yield line
                for claim_id in amended:
                    yield say(narrator.amended(case, claim_id, state.label(claim_id)))
                yield say(narrator.still_holding(case, state))
            case Confession(contradiction=x):
                yield say(narrator.broke(state.label(x.claim)))
                async for line in self._suspect(
                    case, state, task_confess(case, x), history, may_confess=True
                ):
                    yield line
                yield say(narrator.confession_wrap(case, state, rating(state) or "C"))
            case Wrong(card=card, claim=claim, strikes_left=left):
                yield say(narrator.wrong(state.label(claim)))
                async for line in self._suspect(case, state, task_wrong(case, card, claim), history):
                    yield line
                if state.strikes == 1:
                    yield say(narrator.lawyer_rule(case))
                yield say(narrator.countdown(left))
            case Weak(card=card, claim=claim, reason=reason):
                yield say(narrator.weak(state.label(claim)))
                async for line in self._suspect(case, state, task_weak(case, card, claim, reason), history):
                    yield line
            case AlreadyBroken(claim=claim):
                yield say(narrator.already_broken(state.label(claim)))
            case UnknownRef(card=card, claim=claim):
                yield say(narrator.unknown_ref(case, state, card, claim))
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
            case Hint(kind=kind, claim=claim, card=card):
                yield say(narrator.hint(case, state, kind, claim, card))
            case Truth(available=available):
                yield say(narrator.truth(case, available))
            case CaseList(titles=titles, current=current):
                yield say(narrator.case_list(titles, current))
            case GameOver():
                yield say(narrator.game_over())
