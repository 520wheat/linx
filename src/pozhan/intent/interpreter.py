from dataclasses import dataclass

from pozhan.case.model import Case
from pozhan.engine.events import Ask, Event
from pozhan.llm.client import LLM


@dataclass(frozen=True)
class Clarify:
    """看得出想出示，但不确定是哪张卡或哪条证词，需要反问。"""

    card: int | None
    claim: int | None


class RuleMatcher:
    """编号句式和指令的规则匹配。实现见 #8。"""

    def match(self, text: str, case: Case) -> Event | Clarify | None:
        return None


class LLMClassifier:
    """规则未命中时，用大模型判断是不是出示。实现见 #8。"""

    def __init__(self, llm: LLM, model: str) -> None:
        self.llm = llm
        self.model = model

    async def classify(self, text: str, case: Case) -> Event | Clarify:
        return Ask(text)


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
        return await self.classifier.classify(text, case)
