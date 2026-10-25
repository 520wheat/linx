from collections.abc import AsyncIterator
from dataclasses import dataclass

from pozhan.case.model import Case
from pozhan.engine.outcomes import Outcome
from pozhan.engine.state import Interrogation
from pozhan.intent.interpreter import Clarify
from pozhan.llm.client import LLM, Message


@dataclass(frozen=True)
class Line:
    """一轮回复里的一段话。speaker 为 narrator（旁白）或 suspect（嫌疑人）。"""

    speaker: str
    text: str


class Director:
    """实现见 #9。"""

    def __init__(self, llm: LLM | None, model: str) -> None:
        self.llm = llm
        self.model = model

    def emoji(self, case: Case, state: Interrogation) -> str:
        """这一轮的情绪：灵矽只取回复的第一个 emoji，一轮固定一种情绪。"""
        return case.stages[min(state.stage, len(case.stages) - 1)].emoji

    async def speak(
        self,
        case: Case,
        state: Interrogation,
        outcome: Outcome | Clarify,
        history: list[Message],
    ) -> AsyncIterator[Line]:
        yield Line("suspect", "（骨架）嫌疑人还没学会说话。")
