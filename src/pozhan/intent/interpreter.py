from dataclasses import dataclass

from pozhan.case.model import Case
from pozhan.engine.events import Ask, Event
from pozhan.intent.classifier import LLMClassifier
from pozhan.intent.rules import RuleMatcher


@dataclass(frozen=True)
class Clarify:
    """看得出想出示，但不确定是哪张卡或哪条证词，需要反问。"""

    card: int | None
    claim: int | None


class Interpreter:
    def __init__(self, rules: RuleMatcher, classifier: LLMClassifier | None) -> None:
        self.rules = rules
        self.classifier = classifier

    async def interpret(self, text: str, case: Case) -> Event | Clarify:
        matched = self.rules.match(text, case)
        if matched is not None:
            return matched
        if self.classifier is None:
            return Ask(text)
        result = await self.classifier.classify(text, case)
        if isinstance(result, tuple):
            return Clarify(*result)
        return result
