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

    def match(self, text: str, case: Case) -> Event | None:
        """只走规则匹配，零延迟；拿不准时返回 None。"""
        return self.rules.match(text, case)

    async def classify(self, text: str, case: Case) -> Event | Clarify:
        """规则未命中时的大模型分类；没有配置模型时一律当作提问。"""
        if self.classifier is None:
            return Ask(text)
        result = await self.classifier.classify(text, case)
        if isinstance(result, tuple):
            return Clarify(*result)
        return result

    async def interpret(self, text: str, case: Case) -> Event | Clarify:
        matched = self.match(text, case)
        if matched is not None:
            return matched
        return await self.classify(text, case)
