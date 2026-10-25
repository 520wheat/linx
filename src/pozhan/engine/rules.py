"""审讯规则。规则说明以 Proposal #3 的「本期范围」和「验收标准」为准。"""

from dataclasses import replace

from pozhan.case.model import Case, Claim, Contradiction
from pozhan.engine.events import Ask, Command, CommandKind, Event, Present
from pozhan.engine.outcomes import (
    AlreadyBroken,
    Answer,
    Briefing,
    Broke,
    Confession,
    GameOver,
    Hint,
    Lawyer,
    Outcome,
    Quit,
    ReadCard,
    ReadClaims,
    Remaining,
    Repeat,
    Revealed,
    Rules,
    Truth,
    UnknownRef,
    Weak,
    Wrong,
)
from pozhan.engine.state import Interrogation, Phase

# 游戏结束后仍然可以回答的查询类指令
_QUERIES = {
    CommandKind.READ_CLAIMS,
    CommandKind.READ_CARD,
    CommandKind.RULES,
    CommandKind.REPEAT,
    CommandKind.TRUTH,
}


def new_game(case: Case, now: float) -> Interrogation:
    return Interrogation(case_id=case.id, started_at=now, revealed=tuple(c.id for c in case.opening_claims))


def open_topics(case: Case, state: Interrogation) -> list[Claim]:
    """现在问到就会说出口的隐藏证词：有话题、还没说出口、前置证词（如果有）已经戳破。"""
    return [
        c
        for c in case.claims
        if c.unlock is not None
        and c.unlock.topic
        and c.id not in state.revealed
        and (c.unlock.after is None or c.unlock.after in state.broken)
    ]


def rating(state: Interrogation) -> str | None:
    """评级（#55）：只有破案才评。失误 = 出示错误 + 主动要提示 + 卡住后靠他自己说漏。"""
    if state.phase is not Phase.CONFESSED:
        return None
    misses = state.strikes + state.hints + state.blurts
    return "S" if misses == 0 else "A" if misses <= 1 else "B" if misses <= 3 else "C"


def _hint(case: Case, state: Interrogation) -> tuple[Interrogation, Outcome]:
    """逐级提示（#55）：先指方向，同一处再求助就点名答案。每次求助都计入评级。"""
    breakable = {x.claim for x in case.contradictions}
    pending = [c for c in state.revealed if c not in state.broken and c in breakable]
    topics = open_topics(case, state)
    if pending:
        target = ("claim", pending[0])
        if state.hint_target == target:
            x = next(x for x in case.contradictions if x.claim == pending[0])
            hint = Hint("card", claim=pending[0], card=x.card)
        else:
            hint = Hint("claim", claim=pending[0])
    elif topics:
        target = ("topic", topics[0].id)
        hint = Hint("topic", claim=topics[0].id) if state.hint_target == target else Hint("unsaid")
    else:
        return state, Hint("none")
    return replace(state, hints=state.hints + 1, hint_target=target), hint


def stage_for(case: Case, broken: int, confessed: bool) -> int:
    """心理档位按戳破进度分布，最后一档只在认罪时用（#46）。三条谎言、四个档位时和逐条升档一致。"""
    last = len(case.stages) - 1
    if confessed:
        return last
    total = len(case.contradictions)
    if broken == 0 or total <= 1:
        return 0
    return min(last - 1, -(-broken * (last - 1) // (total - 1)))


def seconds_left(case: Case, state: Interrogation, now: float) -> int:
    return max(0, int(case.limits.minutes * 60 - (now - state.started_at)))


def next_slip(case: Case, state: Interrogation) -> Contradiction | None:
    """失言要指向的矛盾：已经说出口、或者问到就能说出口的证词里，编号最小、尚未戳破的那条。

    指向还没说出口的证词时，失言提示的是「该问什么」（#46）。
    """
    reachable = set(state.revealed) | {c.id for c in open_topics(case, state)}
    pending = [x for x in case.contradictions if x.claim not in state.broken and x.claim in reachable]
    return min(pending, key=lambda x: x.claim, default=None)


def apply(case: Case, state: Interrogation, event: Event, now: float) -> tuple[Interrogation, Outcome]:
    if isinstance(event, Command):
        if event.kind is CommandKind.RESTART:
            return new_game(case, now), Briefing()
        if event.kind is CommandKind.QUIT and not state.over:
            return replace(state, phase=Phase.QUIT), Quit()
        if event.kind in _QUERIES:
            return state, _query(case, state, event, now)

    if state.over:
        return state, GameOver()

    if seconds_left(case, state, now) == 0:
        return replace(state, phase=Phase.LAWYER), Lawyer("timeout")

    if isinstance(event, Command):
        if event.kind is CommandKind.START:
            return state, Briefing()
        if event.kind is CommandKind.HINT:
            return _hint(case, state)
        return state, _query(case, state, event, now)
    if isinstance(event, Present):
        return _present(case, state, event)
    return _ask(case, state, event)


def _query(case: Case, state: Interrogation, event: Command, now: float) -> Outcome:
    match event.kind:
        case CommandKind.READ_CLAIMS:
            return ReadClaims()
        case CommandKind.READ_CARD:
            if event.card is None or case.card(event.card) is None:
                return UnknownRef(card=event.card, claim=None)
            return ReadCard(event.card)
        case CommandKind.REPEAT:
            return Repeat()
        case CommandKind.TRUTH:
            return Truth(available=state.over)
        case CommandKind.REMAINING:
            return Remaining(
                strikes_left=case.limits.strikes - state.strikes,
                seconds_left=seconds_left(case, state, now),
            )
        case _:
            return Rules()


# 说出口的证词都戳破了、还剩问到才说的证词时，再问这么多句还没问到，嫌疑人就自己说漏（#53 自对弈发现：
# 玩家问不到话题会一直卡住）。推理游戏的通行做法是提示逐级加强，不让玩家彻底卡死
STUCK_ASKS = 2


def _ask(case: Case, state: Interrogation, event: Ask) -> tuple[Interrogation, Outcome]:
    topics = open_topics(case, state)
    if event.topic is not None and event.topic in {c.id for c in topics}:
        return replace(state, revealed=(*state.revealed, event.topic), idle=0), Revealed(event.topic)
    idle = state.idle + 1
    all_said_broken = all(c in state.broken for c in state.revealed)
    if topics and all_said_broken and idle >= STUCK_ASKS:
        state = replace(state, revealed=(*state.revealed, topics[0].id), idle=0, blurts=state.blurts + 1)
        return state, Revealed(topics[0].id, blurted=True)
    stage = case.stages[state.stage]
    if idle >= stage.slip_every:
        slip = next_slip(case, state)
        if slip is not None:
            return replace(state, idle=0), Answer(question=event.text, slip=slip)
    return replace(state, idle=idle), Answer(question=event.text)


def _present(case: Case, state: Interrogation, event: Present) -> tuple[Interrogation, Outcome]:
    # 玩家说的是「第几条说出口的证词」；还没说出口的序号和不存在的一样处理，不扣机会
    claim_id = state.claim_at(event.claim)
    card_missing = case.card(event.card) is None
    hit = None if card_missing or claim_id is None else case.contradiction(event.card, claim_id)
    if not event.explicit and (hit is None or claim_id in state.broken):
        # 提问时顺口提到了卡：没驳倒就当普通提问，不扣次数，也不念「已经被戳破」（#49）
        return _ask(case, state, Ask(event.text))

    if card_missing or claim_id is None:
        return state, UnknownRef(
            card=event.card if card_missing else None,
            claim=event.claim if claim_id is None else None,
        )

    if claim_id in state.broken:
        return state, AlreadyBroken(claim_id)

    if hit is None and (weak := case.weak_evidence(event.card, claim_id)) is not None:
        return state, Weak(card=event.card, claim=claim_id, reason=weak.reason)
    if hit is None:
        strikes = state.strikes + 1
        if strikes >= case.limits.strikes:
            return replace(state, strikes=strikes, phase=Phase.LAWYER), Lawyer("strikes")
        return replace(state, strikes=strikes), Wrong(
            card=event.card, claim=claim_id, strikes_left=case.limits.strikes - strikes
        )

    broken = (*state.broken, claim_id)
    if len(broken) == len(case.contradictions):
        stage = stage_for(case, len(broken), confessed=True)
        return replace(state, broken=broken, stage=stage, idle=0, phase=Phase.CONFESSED), Confession(hit)
    # 让步里的新谎言：前置证词一戳破，嫌疑人就改口说出来
    revealed = tuple(
        c.id
        for c in case.claims
        if c.unlock is not None
        and not c.unlock.topic
        and c.unlock.after == claim_id
        and c.id not in state.revealed
    )
    stage = stage_for(case, len(broken), confessed=False)
    state = replace(state, broken=broken, stage=stage, idle=0, revealed=(*state.revealed, *revealed))
    return state, Broke(hit, stage, revealed)
