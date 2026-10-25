"""出示判定更公平（#49）：间接证据和顺口提到的卡不扣次数。用正式案件第二版测。"""

import pytest
import yaml

from pozhan.case import load_case, parse_case, validate
from pozhan.director import Director
from pozhan.engine import AlreadyBroken, Answer, Broke, Present, Weak, Wrong, apply, new_game
from tests.conftest import ROOT

V2 = ROOT / "cases" / "golden-watch.yaml"


@pytest.fixture
def v2():
    return load_case(V2)


def test_weak_evidence_costs_nothing(v2):
    state, out = apply(v2, new_game(v2, 0), Present(card=1, claim=1), 1)
    assert isinstance(out, Weak) and out.reason and state.strikes == 0


async def test_weak_evidence_is_announced_then_deflected(v2):
    state, out = apply(v2, new_game(v2, 0), Present(card=1, claim=1), 1)
    lines = [x async for x in Director(llm=None, model="").speak(v2, state, out, [])]
    assert lines[0].text.startswith("这张卡说明了点什么，但还不够硬，驳不倒证词一")
    assert lines[1].speaker == "suspect"


def test_mentioning_a_card_in_a_question_is_not_a_strike(v2):
    state, out = apply(
        v2, new_game(v2, 0), Present(card=3, claim=1, text="便利贴怎么回事", explicit=False), 1
    )
    assert isinstance(out, Answer) and state.strikes == 0 and state.idle == 1


def test_mentioning_a_card_that_breaks_the_claim_still_counts(v2):
    _, out = apply(v2, new_game(v2, 0), Present(card=2, claim=1, text="电梯拍到你了", explicit=False), 1)
    assert isinstance(out, Broke)


def test_mentioning_a_used_card_does_not_nag_about_broken_claims(v2):
    state, _ = apply(v2, new_game(v2, 0), Present(card=2, claim=1), 1)
    _, out = apply(v2, state, Present(card=2, claim=1, text="你九点半上楼干嘛", explicit=False), 2)
    assert isinstance(out, Answer)
    _, out = apply(v2, state, Present(card=2, claim=1), 2)
    assert isinstance(out, AlreadyBroken)  # 明确出示时照常提醒


def test_explicit_wrong_presentation_still_costs_a_strike(v2):
    state, out = apply(v2, new_game(v2, 0), Present(card=3, claim=1), 1)
    assert isinstance(out, Wrong) and state.strikes == 1


def test_weak_evidence_must_not_also_break_the_claim():
    data = yaml.safe_load(V2.read_text(encoding="utf-8"))
    data["weak"].append({"card": 2, "claim": 1, "reason": "x"})
    assert "weak-is-breaker" in {p.rule for p in validate(parse_case(data))}
