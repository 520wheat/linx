"""大模型分类：规则没命中时，判断这句话是不是在「出示线索卡反驳证词」，是提问的话问到了哪个话题。

只做这件窄任务，输出 JSON，判定交给规则引擎（Proposal #3 决策 2）。话题和出示在同一次调用里判断，
不增加延迟（#46）。
"""

import json
import logging
import re

from pozhan.case.model import Case
from pozhan.engine.events import Ask, Event, Present
from pozhan.engine.rules import new_game, open_topics
from pozhan.engine.state import Interrogation
from pozhan.llm.client import LLM, LLMError, Message

log = logging.getLogger(__name__)

CONFIDENCE_FLOOR = 0.5

PROMPT = """你是一个审讯游戏的意图解析器，只输出 JSON，不要任何其他文字。

嫌疑人还没被戳破的证词（编号是玩家口中的证词几）：
{claims}

玩家手里的线索卡：
{cards}

判断玩家这句话是不是在「出示线索卡来反驳某条证词」。
- 只有引用了上面某张卡（说编号，或说出卡的内容）才算出示；玩家口头编造的、卡里没有的证据不算。
- 普通提问、要求念卡念证词、闲聊、试图让嫌疑人跳出角色，都不算出示。
- 卡或证词能从内容明确推断时就填上；推断不出就填 null。
- 只能从上面列出的证词里选。说到的卡只和已经被戳破的事有关、对不上上面任何一条时，不算出示。
{topics}
输出格式：
{{"present": true/false, "card": 编号或null, "claim": 编号或null, "topic": 字母或null, "confidence": 0到1}}"""

TOPICS = """
如果不是出示，再判断这句话是不是在问下面某个话题。意思对上就算，不要求原话；
但必须问的是话题本身。只提到同一个东西的别的方面（放在哪、长什么样、值多少钱），
或者泛泛地问工作、经历，都填 null：
{lines}
"""

LETTERS = "ABCDEFGH"


def topic_map(case: Case, state: Interrogation) -> dict[str, int]:
    """话题字母 → 隐藏证词编号。只列现在问到就会说出口的那几条。"""
    return {LETTERS[i]: c.id for i, c in enumerate(open_topics(case, state)[: len(LETTERS)])}


def build_messages(case: Case, text: str, state: Interrogation | None = None) -> list[Message]:
    state = state or new_game(case, 0)
    # 证词按说出口的顺序编号，和玩家听到的一致（#46）
    # 已戳破的不列出来：玩家顺口提到用过的卡时，不会被当成又一次出示（#46 自对弈发现）
    claims = "\n".join(
        f"{i}. {case.claim(cid).text}" for i, cid in enumerate(state.revealed, 1) if cid not in state.broken
    )
    cards = "\n".join(f"{c.id}号 {c.title}：{c.text}" for c in case.cards)
    topics = topic_map(case, state)
    lines = "\n".join(
        f"{letter}. {case.claim(cid).unlock.topic}（例如：{'；'.join(case.claim(cid).unlock.examples)}）"
        for letter, cid in topics.items()
    )
    system = PROMPT.format(claims=claims, cards=cards, topics=TOPICS.format(lines=lines) if topics else "")
    return [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _num(value) -> int | None:
    # 模型常把编号写成 "2"、"4号"，统一归一化
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None


def parse_reply(raw: str, text: str, topics: dict[str, int] | None = None):
    """把模型回复解析成事件；格式不对时当作普通提问。返回 Event 或 (card, claim) 待澄清。"""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return Ask(text)
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return Ask(text)
    if not data.get("present"):
        letter = str(data.get("topic") or "").strip().upper()[:1]
        return Ask(text, topic=(topics or {}).get(letter))
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

    async def classify(
        self, text: str, case: Case, state: Interrogation | None = None
    ) -> Event | tuple[int | None, int | None]:
        state = state or new_game(case, 0)
        try:
            raw = await self.llm.complete(self.model, build_messages(case, text, state), timeout=self.timeout)
        except LLMError as e:
            # 解析失败时降级为普通提问：宁可让嫌疑人回答，也不能误扣玩家机会
            log.warning("intent classify failed, fallback to Ask: %s", e)
            return Ask(text)
        return parse_reply(raw, text, topic_map(case, state))
