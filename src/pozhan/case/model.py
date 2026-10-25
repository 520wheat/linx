from dataclasses import dataclass, field


@dataclass(frozen=True)
class Unlock:
    """隐藏证词什么时候说出口（#46）。

    只有 after：证词 after 被戳破时，嫌疑人改口说出这条（让步里的新谎言）。
    有 topic：侦探问到这个话题才说出口；同时有 after 时，要等证词 after 被戳破之后问才算。
    """

    topic: str = ""
    examples: tuple[str, ...] = ()
    after: int | None = None


@dataclass(frozen=True)
class Claim:
    """嫌疑人的一条证词。unlock 为空的在开场陈述里说出口，其余要靠追问或戳破别的证词逼出来。"""

    id: int
    text: str
    lie: bool
    unlock: Unlock | None = None


@dataclass(frozen=True)
class Card:
    """玩家手里的一张实体线索卡。"""

    id: int
    title: str
    text: str


@dataclass(frozen=True)
class Contradiction:
    """「哪张卡能戳破哪条证词」，以及戳破后嫌疑人要让步承认什么。"""

    card: int
    claim: int
    concession: str
    slip: str = ""  # 卡关时嫌疑人可能说漏的破绽，指向这条矛盾


@dataclass(frozen=True)
class Stage:
    """嫌疑人的心理档位。每戳破一条矛盾升一档，最后一档即认罪。"""

    name: str
    emoji: str
    tone: str
    slip_every: int = 6  # 连续多少问没有进展就失言一次


@dataclass(frozen=True)
class Suspect:
    name: str
    persona: str
    truth: tuple[str, ...] = ()  # 真相，只在服务端使用，用来约束嫌疑人不编造
    # 认罪时要说出的内容。最后被戳破的可能是任何一条证词（#46），所以认罪内容不能只写在某条矛盾的让步里
    confession: str = ""


@dataclass(frozen=True)
class TimelineStep:
    """结局页真相时间线的一步：什么时候、发生了什么、对应哪张线索卡。"""

    text: str
    time: str = ""
    card: int | None = None


@dataclass(frozen=True)
class Limits:
    strikes: int = 3  # 出示错误几次律师到场
    minutes: int = 15  # 审讯最长时长


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    briefing: str
    suspect: Suspect
    claims: tuple[Claim, ...]
    cards: tuple[Card, ...]
    contradictions: tuple[Contradiction, ...]
    stages: tuple[Stage, ...]
    reveal: str
    limits: Limits = field(default_factory=Limits)
    timeline: tuple[TimelineStep, ...] = ()  # 可选，陪玩屏结局页使用（#37）

    @property
    def opening_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.unlock is None)

    def claim(self, claim_id: int) -> Claim | None:
        return next((c for c in self.claims if c.id == claim_id), None)

    def card(self, card_id: int) -> Card | None:
        return next((c for c in self.cards if c.id == card_id), None)

    def contradiction(self, card_id: int, claim_id: int) -> Contradiction | None:
        return next((x for x in self.contradictions if x.card == card_id and x.claim == claim_id), None)
