"""审讯规则。规则说明以 Proposal #3 的「本期范围」和「验收标准」为准。"""

from dataclasses import replace

from pozhan.case.model import Case, Contradiction
from pozhan.engine.events import Ask, Command, CommandKind, Event, Present
from pozhan.engine.outcomes import (
    AlreadyBroken,
    Answer,
    Briefing,
    Broke,
    Confession,
    GameOver,
    Lawyer,
    Outcome,
    Quit,
    ReadCard,
    ReadClaims,
    Remaining,
    Repeat,
    Rules,
    UnknownRef,
    Wrong,
)
from pozhan.engine.state import Interrogation, Phase

# 游戏结束后仍然可以回答的查询类指令
_QUERIES = {CommandKind.READ_CLAIMS, CommandKind.READ_CARD, CommandKind.RULES, CommandKind.REPEAT}


def new_game(case: Case, now: float) -> Interrogation:
    return Interrogation(case_id=case.id, started_at=now)


def seconds_left(case: Case, state: Interrogation, now: float) -> int:
    return max(0, int(case.limits.minutes * 60 - (now - state.started_at)))


def next_slip(case: Case, state: Interrogation) -> Contradiction | None:
    """失言要指向的矛盾：编号最小、尚未戳破的那条证词。"""
    pending = [x for x in case.contradictions if x.claim not in state.broken]
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
        case CommandKind.REMAINING:
            return Remaining(
                strikes_left=case.limits.strikes - state.strikes,
                seconds_left=seconds_left(case, state, now),
            )
        case _:
            return Rules()


def _ask(case: Case, state: Interrogation, event: Ask) -> tuple[Interrogation, Outcome]:
    idle = state.idle + 1
    stage = case.stages[state.stage]
    if idle >= stage.slip_every:
        slip = next_slip(case, state)
        if slip is not None:
            return replace(state, idle=0), Answer(question=event.text, slip=slip)
    return replace(state, idle=idle), Answer(question=event.text)


def _present(case: Case, state: Interrogation, event: Present) -> tuple[Interrogation, Outcome]:
    card_missing = case.card(event.card) is None
    claim_missing = case.claim(event.claim) is None
    if card_missing or claim_missing:
        return state, UnknownRef(
            card=event.card if card_missing else None,
            claim=event.claim if claim_missing else None,
        )

    if event.claim in state.broken:
        return state, AlreadyBroken(event.claim)

    hit = case.contradiction(event.card, event.claim)
    if hit is None:
        strikes = state.strikes + 1
        if strikes >= case.limits.strikes:
            return replace(state, strikes=strikes, phase=Phase.LAWYER), Lawyer("strikes")
        return replace(state, strikes=strikes), Wrong(
            card=event.card, claim=event.claim, strikes_left=case.limits.strikes - strikes
        )

    broken = (*state.broken, event.claim)
    stage = min(state.stage + 1, len(case.stages) - 1)
    if len(broken) == len(case.contradictions):
        return replace(state, broken=broken, stage=stage, idle=0, phase=Phase.CONFESSED), Confession(hit)
    return replace(state, broken=broken, stage=stage, idle=0), Broke(hit, stage)
