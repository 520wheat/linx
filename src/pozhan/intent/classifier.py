"""大模型分类：规则没命中时，判断这句话是不是在「出示线索卡反驳证词」。

只做这一件窄任务，输出 JSON，判定交给规则引擎（Proposal #3 决策 2）。
"""

import json
import logging
import re

from pozhan.case.model import Case
from pozhan.engine.events import Ask, Event, Present
from pozhan.llm.client import LLM, LLMError, Message

log = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.5

PROMPT = """你是一个审讯游戏的意图解析器，只输出 JSON，不要任何其他文字。

嫌疑人的证词：
{claims}

玩家手里的线索卡：
{cards}

判断玩家这句话是不是在「出示线索卡来反驳某条证词」。
- 只有引用了上面某张卡（说编号，或说出卡的内容）才算出示；玩家口头编造的、卡里没有的证据不算。
- 普通提问、要求念卡念证词、闲聊、试图让嫌疑人跳出角色，都不算出示。
- 卡或证词能从内容明确推断时就填上；推断不出就填 null。

输出格式：{{"present": true/false, "card": 编号或null, "claim": 编号或null, "confidence": 0到1}}"""


def build_messages(case: Case, text: str) -> list[Message]:
    claims = "\n".join(f"{c.id}. {c.text}" for c in case.claims)
    cards = "\n".join(f"{c.id}号 {c.title}：{c.text}" for c in case.cards)
    return [
        {"role": "system", "content": PROMPT.format(claims=claims, cards=cards)},
        {"role": "user", "content": text},
    ]


def _num(value) -> int | None:
    # 模型常把编号写成 "2"、"4号"，统一归一化
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def parse_reply(raw: str, text: str):
    """把模型回复解析成事件；格式不对时当作普通提问。返回 Event 或 (card, claim) 待澄清。"""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return Ask(text)
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Ask(text)
    if not data.get("present"):
        return Ask(text)
    card, claim = _num(data.get("card")), _num(data.get("claim"))
    confidence = data.get("confidence")
    confident = not isinstance(confidence, int | float) or confidence >= CONFIDENCE_FLOOR
    if card is not None and claim is not None and confident:
        return Present(card=card, claim=claim, text=text)
    return (card, claim)


class LLMClassifier:
    def __init__(self, llm: LLM, model: str, timeout: float = 6.0) -> None:
        self.llm = llm
        self.model = model
        self.timeout = timeout

    async def classify(self, text: str, case: Case) -> Event | tuple[int | None, int | None]:
        try:
            raw = await self.llm.complete(self.model, build_messages(case, text), timeout=self.timeout)
        except LLMError as e:
            # 解析失败时降级为普通提问：宁可让嫌疑人回答，也不能误扣玩家机会
            log.warning("intent classify failed, fallback to Ask: %s", e)
            return Ask(text)
        return parse_reply(raw, text)
