"""审讯规则测试。场景以「年会夜的金表」为例：卡 2→证词 1、卡 3→证词 2、卡 4→证词 3，卡 1 是干扰卡。"""

import pytest

from pozhan.engine import (
    AlreadyBroken,
    Answer,
    Ask,
    Briefing,
    Broke,
    Command,
    CommandKind,
    Confession,
    GameOver,
    Lawyer,
    Phase,
    Present,
    Quit,
    ReadCard,
    ReadClaims,
    Remaining,
    Repeat,
    Rules,
    UnknownRef,
    Wrong,
    apply,
    new_game,
)

T0 = 1_000_000.0


@pytest.fixture
def start(case):
    return new_game(case, T0)


def play(case, state, *events, now=T0 + 10):
    outcome = None
    for e in events:
        state, outcome = apply(case, state, e, now)
    return state, outcome


def test_start_gives_briefing(case, start):
    state, outcome = play(case, start, Command(CommandKind.START))
    assert outcome == Briefing()
    assert state.phase is Phase.INTERROGATING and state.stage == 0


def test_correct_presentation_breaks_claim_and_raises_stage(case, start):
    state, outcome = play(case, start, Present(card=2, claim=1))
    assert isinstance(outcome, Broke)
    assert outcome.contradiction.claim == 1 and outcome.stage == 1
    assert state.broken == (1,) and state.stage == 1 and state.strikes == 0


def test_wrong_presentation_costs_a_strike(case, start):
    state, outcome = play(case, start, Present(card=1, claim=1))
    assert outcome == Wrong(card=1, claim=1, strikes_left=2)
    assert state.strikes == 1 and state.stage == 0


def test_already_broken_claim_costs_nothing(case, start):
    state, outcome = play(case, start, Present(card=2, claim=1), Present(card=1, claim=1))
    assert outcome == AlreadyBroken(1)
    assert state.strikes == 0


def test_unknown_card_or_claim_costs_nothing(case, start):
    state, outcome = play(case, start, Present(card=9, claim=1))
    assert outcome == UnknownRef(card=9, claim=None)
    state, outcome = play(case, state, Present(card=2, claim=7))
    assert outcome == UnknownRef(card=None, claim=7)
    assert state.strikes == 0


def test_three_wrong_presentations_bring_the_lawyer(case, start):
    state, outcome = play(case, start, Present(1, 1), Present(1, 2), Present(2, 3))
    assert outcome == Lawyer("strikes")
    assert state.phase is Phase.LAWYER


def test_timeout_brings_the_lawyer(case, start):
    state, outcome = play(case, start, Ask("你在哪"), now=T0 + 15 * 60)
    assert outcome == Lawyer("timeout")
    assert state.over


def test_winning_path_ends_in_confession(case, start):
    state, outcome = play(case, start, Present(2, 1), Present(3, 2))
    assert isinstance(outcome, Broke) and outcome.stage == 2
    state, outcome = play(case, state, Present(4, 3))
    assert isinstance(outcome, Confession)
    assert state.phase is Phase.CONFESSED and state.stage == 3


def test_contradictions_can_be_broken_in_any_order(case, start):
    state, outcome = play(case, start, Present(4, 3), Present(2, 1), Present(3, 2))
    assert isinstance(outcome, Confession)


def test_questions_without_progress_trigger_a_slip(case, start):
    asks = [Ask(f"问题{i}") for i in range(6)]
    state, outcome = play(case, start, *asks[:5])
    assert outcome == Answer("问题4") and state.idle == 5
    state, outcome = play(case, state, asks[5])
    assert isinstance(outcome, Answer) and outcome.slip is not None
    assert outcome.slip.claim == 1  # 指向编号最小、未戳破的证词
    assert state.idle == 0


def test_slip_points_to_next_unbroken_claim(case, start):
    state, _ = play(case, start, Present(2, 1))  # 升到「狡辩」，slip_every = 5
    state, outcome = play(case, state, *[Ask("嗯") for _ in range(5)])
    assert outcome.slip.claim == 2


def test_progress_resets_idle_counter(case, start):
    state, _ = play(case, start, Ask("a"), Ask("b"), Present(2, 1))
    assert state.idle == 0


def test_queries(case, start):
    assert play(case, start, Command(CommandKind.READ_CLAIMS))[1] == ReadClaims()
    assert play(case, start, Command(CommandKind.READ_CARD, card=3))[1] == ReadCard(3)
    assert play(case, start, Command(CommandKind.READ_CARD, card=8))[1] == UnknownRef(card=8, claim=None)
    assert play(case, start, Command(CommandKind.RULES))[1] == Rules()
    assert play(case, start, Command(CommandKind.REPEAT))[1] == Repeat()
    state, _ = play(case, start, Present(1, 1))
    assert play(case, state, Command(CommandKind.REMAINING), now=T0 + 60)[1] == Remaining(
        strikes_left=2, seconds_left=14 * 60
    )


def test_quit(case, start):
    state, outcome = play(case, start, Command(CommandKind.QUIT))
    assert outcome == Quit() and state.phase is Phase.QUIT


def test_after_game_over_only_restart_and_queries_work(case, start):
    over, _ = play(case, start, Present(1, 1), Present(1, 2), Present(1, 3))
    assert play(case, over, Ask("还在吗"))[1] == GameOver()
    assert play(case, over, Present(2, 1))[1] == GameOver()
    assert play(case, over, Command(CommandKind.READ_CLAIMS))[1] == ReadClaims()
    state, outcome = play(case, over, Command(CommandKind.RESTART), now=T0 + 100)
    assert outcome == Briefing()
    assert state.phase is Phase.INTERROGATING and state.strikes == 0 and state.started_at == T0 + 100
