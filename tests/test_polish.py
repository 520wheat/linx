"""结算评级、提示指令与更短的结局（#55）。用正式案件第二版测。"""

import pytest

from pozhan.case import load_case
from pozhan.director import Director, narrator
from pozhan.engine import Ask, Command, CommandKind, Hint, Present, Truth, apply, new_game, rating
from pozhan.intent.rules import match
from tests.conftest import ROOT

WIN = [Present(2, 1), Present(6, 3), Present(4, 2), Present(5, 4), Ask("密码", topic=4), Present(3, 5)]


@pytest.fixture
def v2():
    return load_case(ROOT / "cases" / "golden-watch.yaml")


def play(case, moves):
    state = new_game(case, 0)
    for m in moves:
        state, out = apply(case, state, m, 1)
    return state, out


def test_flawless_win_is_s_and_one_miss_is_a(v2):
    assert rating(play(v2, WIN)[0]) == "S"
    assert rating(play(v2, [Present(3, 1), *WIN])[0]) == "A"
    assert (
        rating(play(v2, [Command(CommandKind.HINT), Command(CommandKind.HINT), Present(1, 2), *WIN])[0])
        == "B"
    )
    assert rating(new_game(v2, 0)) is None


async def test_win_announces_the_rating_instead_of_the_whole_truth(v2):
    state, out = play(v2, [Present(3, 1), *WIN])
    lines = [x async for x in Director(llm=None, model="").speak(v2, state, out, [])]
    wrap = lines[-1].text
    assert wrap.startswith("案件告破！评级A：出示错一次。") and v2.reveal not in wrap and "讲讲真相" in wrap


def test_truth_only_after_the_game(v2):
    state = new_game(v2, 0)
    _, out = apply(v2, state, Command(CommandKind.TRUTH), 1)
    assert out == Truth(available=False)
    state, _ = play(v2, WIN)
    _, out = apply(v2, state, Command(CommandKind.TRUTH), 2)
    assert out == Truth(available=True)
    assert narrator.truth(v2, True) == f"真相是：{v2.reveal}"


def test_hints_escalate_on_the_same_spot_and_count_as_misses(v2):
    state = new_game(v2, 0)
    state, out = apply(v2, state, Command(CommandKind.HINT), 1)
    assert out == Hint("claim", claim=1) and state.hints == 1
    assert narrator.hint(v2, state, out.kind, out.claim, out.card).startswith("盯紧证词一")
    state, out = apply(v2, state, Command(CommandKind.HINT), 2)
    assert out == Hint("card", claim=1, card=2) and state.hints == 2
    assert "二号卡「电梯监控截图」" in narrator.hint(v2, state, out.kind, out.claim, out.card)


def test_hint_points_at_the_unasked_topic_when_everything_said_is_broken(v2):
    state, _ = play(v2, [Present(2, 1), Present(6, 3), Present(4, 2), Present(5, 4)])
    state, out = apply(v2, state, Command(CommandKind.HINT), 1)
    assert out == Hint("unsaid")
    state, out = apply(v2, state, Command(CommandKind.HINT), 2)
    assert out == Hint("topic", claim=4)
    assert narrator.hint(v2, state, out.kind, out.claim, out.card) == "试着问他：你知道保险柜密码吗。"


def test_blurting_counts_against_the_rating(v2):
    state, _ = play(v2, [Present(2, 1), Present(6, 3), Present(4, 2), Present(5, 4), Ask("a"), Ask("b")])
    assert state.blurts == 1
    state, _ = apply(v2, state, Present(3, 5), 1)
    assert rating(state) == "A" and "他自己说漏" in narrator.rating_reason(state)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("给点提示", CommandKind.HINT),
        ("我卡住了", CommandKind.HINT),
        ("提示", CommandKind.HINT),
        ("讲讲真相", CommandKind.TRUTH),
        ("真相是什么", CommandKind.TRUTH),
        ("再审一次", CommandKind.RESTART),
    ],
)
def test_new_commands_are_matched_without_the_model(v2, text, kind):
    assert match(text, v2) == Command(kind)
