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

    if len(case.stages) != len(case.contradictions) + 1:
        add(
            "stage-count",
            f"档位数应为矛盾数 + 1（{len(case.contradictions) + 1}），现在是 {len(case.stages)}",
        )
    for s in case.stages:
        if s.slip_every < 1:
            add("slip-every", f"档位「{s.name}」的 slip_every 必须大于 0")

    for x in case.contradictions:
        if not x.slip:
            add("has-slip", f"矛盾（卡 {x.card} × 证词 {x.claim}）缺少失言提示 slip")

    for step in case.timeline:
        if step.card is not None and step.card not in card_ids:
            add("refs-exist", f"时间线「{step.text[:12]}」引用了不存在的线索卡 {step.card}")

    if case.limits.strikes < 1 or case.limits.minutes < 1:
        add("limits", "律师倒计时的次数和分钟数都必须大于 0")

    return problems
