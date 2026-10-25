from collections import Counter
from dataclasses import dataclass

from pozhan.case.model import Case


@dataclass(frozen=True)
class Problem:
    """校验发现的一个问题，message 直接给案件作者看。"""

    rule: str
    message: str


def _duplicates(ids: list[int]) -> list[int]:
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def _reachable(case: Case, claim_id: int) -> bool:
    """沿 unlock.after 往前追，最终要追到一条开场证词，中途不能成环。"""
    seen: set[int] = set()
    claim = case.claim(claim_id)
    while claim is not None and claim.unlock is not None and claim.unlock.after is not None:
        if claim.id in seen:
            return False
        seen.add(claim.id)
        claim = case.claim(claim.unlock.after)
    return claim is not None


def validate(case: Case) -> list[Problem]:
    """检查案件是否公平、可解。返回空列表表示通过。"""
    problems: list[Problem] = []

    def add(rule: str, message: str) -> None:
        problems.append(Problem(rule, message))

    for kind, ids in (("证词", [c.id for c in case.claims]), ("线索卡", [c.id for c in case.cards])):
        for dup in _duplicates(ids):
            add("unique-ids", f"{kind}编号 {dup} 重复")

    claim_ids = {c.id for c in case.claims}
    card_ids = {c.id for c in case.cards}
    for x in case.contradictions:
        if x.card not in card_ids:
            add("refs-exist", f"矛盾引用了不存在的线索卡 {x.card}")
        if x.claim not in claim_ids:
            add("refs-exist", f"矛盾引用了不存在的证词 {x.claim}")

    breakers = Counter(x.claim for x in case.contradictions)
    for claim in case.claims:
        n = breakers.get(claim.id, 0)
        if claim.lie and n != 1:
            add("one-breaker-per-lie", f"谎言证词 {claim.id} 应该恰好被一张卡戳破，现在是 {n} 张")
        if not claim.lie and n:
            add("truths-unbreakable", f"真话证词 {claim.id} 不应该能被戳破")

    if not any(c.lie for c in case.claims):
        add("has-lies", "至少要有一条谎言证词")

    used_cards = {x.card for x in case.contradictions}
    if not card_ids - used_cards:
        add("has-distractor", "至少要有一张不能戳破任何证词的干扰卡")

    # 最后一档留给认罪；其余档位按戳破进度分布（#46），所以档位数不必等于矛盾数 + 1
    if not 2 <= len(case.stages) <= len(case.contradictions) + 1:
        add(
            "stage-count",
            f"档位数应在 2 到矛盾数 + 1（{len(case.contradictions) + 1}）之间，现在是 {len(case.stages)}",
        )
    for s in case.stages:
        if s.slip_every < 1:
            add("slip-every", f"档位「{s.name}」的 slip_every 必须大于 0")

    for x in case.contradictions:
        if not x.slip:
            add("has-slip", f"矛盾（卡 {x.card} × 证词 {x.claim}）缺少失言提示 slip")

    if not case.opening_claims:
        add("has-opening", "至少要有一条开场就说出口的证词（不写 unlock）")
    topics: Counter[str] = Counter()
    for c in case.claims:
        u = c.unlock
        if u is None:
            continue
        if u.after is not None and u.after not in claim_ids:
            add("refs-exist", f"证词 {c.id} 的 unlock.after 引用了不存在的证词 {u.after}")
        if u.after == c.id:
            add("unlock-cycle", f"证词 {c.id} 不能在自己被戳破之后解锁")
        if not u.topic and u.after is None:
            add("unlock-empty", f"证词 {c.id} 的 unlock 至少要写 topic 或 after")
        if u.topic:
            topics[u.topic] += 1
            if len(u.examples) < 2:
                add("unlock-examples", f"证词 {c.id} 的话题「{u.topic}」至少要给两个提问例句")
    for topic, n in topics.items():
        if n > 1:
            add("unique-topics", f"话题「{topic}」被 {n} 条证词使用，问到时不知道该说哪条")
    for c in case.claims:
        if not _reachable(case, c.id):
            add("unlock-reachable", f"证词 {c.id} 的解锁链条有环，永远说不出口")

    for step in case.timeline:
        if step.card is not None and step.card not in card_ids:
            add("refs-exist", f"时间线「{step.text[:12]}」引用了不存在的线索卡 {step.card}")

    for w in case.weak:
        if w.card not in card_ids or w.claim not in claim_ids:
            add("refs-exist", f"间接证据（卡 {w.card} × 证词 {w.claim}）引用了不存在的卡或证词")
        if case.contradiction(w.card, w.claim) is not None:
            add("weak-is-breaker", f"卡 {w.card} 能戳破证词 {w.claim}，不能同时登记为间接证据")

    if case.limits.strikes < 1 or case.limits.minutes < 1:
        add("limits", "律师倒计时的次数和分钟数都必须大于 0")

    return problems
