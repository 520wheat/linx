"""追问解锁（#46）：隐藏证词要问出来，改口出新谎言，证词按说出口的顺序编号。用正式案件第二版测。"""

import json
from collections import deque

import pytest
import yaml

from pozhan.case import load_case, parse_case, validate
from pozhan.director import Director, narrator
from pozhan.engine import (
    Answer,
    Ask,
    Broke,
    Confession,
    Present,
    Revealed,
    UnknownRef,
    Wrong,
    apply,
    new_game,
    open_topics,
)
from pozhan.engine.rules import stage_for
from pozhan.intent.classifier import build_messages, parse_reply, topic_map
from pozhan.screen import build_snapshot
from pozhan.session.store import Session
from tests.conftest import CASES, ROOT

V2 = ROOT / "cases" / "golden-watch.yaml"


@pytest.fixture
def v2():
    return load_case(V2)


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_shipped_cases_are_valid(path):
    assert validate(load_case(path)) == []


def test_only_opening_claims_are_said_at_first(v2):
    state = new_game(v2, 0)
    assert state.revealed == (1, 2)
    assert narrator.opening_statement(v2).count("第") == 2
    assert v2.claim(4).text not in narrator.opening_statement(v2)
    assert [c.id for c in open_topics(v2, state)] == [4]


def test_unsaid_claim_numbers_are_unknown_not_strikes(v2):
    state = new_game(v2, 0)
    state, out = apply(v2, state, Present(card=6, claim=3), 1)
    assert out == UnknownRef(card=None, claim=3) and state.strikes == 0
    assert narrator.unknown_ref(v2, state, None, 3) == "没有第三条证词，他到现在只说过两条。"


def test_breaking_a_claim_can_amend_it_into_a_new_lie(v2):
    state, out = apply(v2, new_game(v2, 0), Present(card=2, claim=1), 1)
    assert isinstance(out, Broke) and out.revealed == (3,)
    assert state.revealed == (1, 2, 3) and state.label(3) == 3
    state, out = apply(v2, state, Present(card=6, claim=3), 2)
    assert isinstance(out, Broke) and out.contradiction.claim == 3


def test_asking_the_topic_reveals_the_hidden_claim_in_spoken_order(v2):
    state, out = apply(v2, new_game(v2, 0), Ask("你知道保险柜密码吗", topic=4), 1)
    assert out == Revealed(4) and state.label(4) == 3 and state.idle == 0
    # 已经说出口了，再问只是普通提问
    _, again = apply(v2, state, Ask("密码到底谁知道", topic=4), 2)
    assert isinstance(again, Answer)
    # 证词 3 现在指的是密码那条
    state, out = apply(v2, state, Present(card=3, claim=3), 3)
    assert isinstance(out, Broke) and out.contradiction.claim == 4


def test_topic_that_is_not_open_is_an_ordinary_question(v2):
    _, out = apply(v2, new_game(v2, 0), Ask("你去储物间拿什么", topic=3), 1)
    assert isinstance(out, Answer)


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_presenting_without_asking_can_never_win(path):
    """每个正式案件都穷举所有「只出示、不提问」的走法：律师到场之前不可能让嫌疑人认罪。"""
    v2 = load_case(path)
    start = new_game(v2, 0)
    queue, seen = deque([start]), {start}
    while queue:
        state = queue.popleft()
        for card in range(1, len(v2.cards) + 1):
            for label in range(1, len(state.revealed) + 1):
                nxt, out = apply(v2, state, Present(card=card, claim=label), 1)
                assert not isinstance(out, Confession)
                if not nxt.over and nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)


def test_full_solution_with_one_question(v2):
    state = new_game(v2, 0)
    moves = [
        Present(2, 1),  # 包厢 → 改口储物间（证词三）
        Present(6, 3),
        Present(4, 2),  # 没碰过 → 改口展台（证词四）
        Present(5, 4),
        Ask("保险柜密码都有谁知道", topic=4),  # 证词五
        Present(3, 5),
    ]
    stages = []
    for move in moves:
        state, out = apply(v2, state, move, 1)
        stages.append(state.stage)
    assert isinstance(out, Confession) and state.strikes == 0
    assert stages == [1, 1, 2, 2, 2, 3]  # 「崩溃」只留给认罪那一刻


def test_stage_mapping_matches_the_old_one_for_three_lies(case):
    assert [stage_for(case, b, b == 3) for b in range(4)] == [0, 1, 2, 3]


def test_wrong_reports_the_spoken_number(v2):
    state, _ = apply(v2, new_game(v2, 0), Ask("密码", topic=4), 1)
    state, out = apply(v2, state, Present(card=1, claim=3), 2)
    assert out == Wrong(card=1, claim=4, strikes_left=2)
    assert state.label(out.claim) == 3


async def test_revealed_claim_is_spoken_verbatim(v2):
    state, out = apply(v2, new_game(v2, 0), Ask("密码", topic=4), 1)
    lines = [x async for x in Director(llm=None, model="").speak(v2, state, out, [])]
    assert [x.speaker for x in lines] == ["suspect", "narrator"]
    assert lines[0].text == v2.claim(4).text and lines[1].text == "记下了，这是证词三。"


async def test_amended_claim_is_restated_by_the_narrator(v2):
    state, out = apply(v2, new_game(v2, 0), Present(card=2, claim=1), 1)
    lines = [x async for x in Director(llm=None, model="").speak(v2, state, out, [])]
    texts = [x.text for x in lines]
    assert texts[0] == "证词一被戳破了！"
    assert f"他改口了：{v2.claim(3).text}这是证词三。" in texts
    assert texts[-1] == "他还在坚持证词二、证词三。"
    assert narrator.read_claims(v2, state).startswith("证词一（已被戳破）")


def test_classifier_maps_topic_letters_to_hidden_claims(v2):
    state = new_game(v2, 0)
    topics = topic_map(v2, state)
    assert topics == {"A": 4}
    assert parse_reply('{"present": false, "topic": "A"}', "t", topics) == Ask("t", topic=4)
    assert parse_reply('{"present": false, "topic": "Z"}', "t", topics) == Ask("t")
    assert parse_reply('{"present": false, "topic": null}', "t", topics) == Ask("t")
    system = build_messages(v2, "t", state)[0]["content"]
    assert "A. 保险柜密码" in system and v2.claim(4).text not in system
    # 说出口以后就不再作为话题列出，证词列表按说出口的顺序编号
    state, _ = apply(v2, state, Ask("密码", topic=4), 1)
    system = build_messages(v2, "t", state)[0]["content"]
    assert "话题" not in system and f"3. {v2.claim(4).text}" in system


def test_screen_never_shows_unsaid_claims(v2):
    session = Session(key="k", state=new_game(v2, 0))
    blob = json.dumps(build_snapshot(v2, session, 0), ensure_ascii=False)
    for hidden in (3, 4, 5):
        assert v2.claim(hidden).text not in blob
    session.state, _ = apply(v2, session.state, Ask("密码", topic=4), 1)
    snap = build_snapshot(v2, session, 1)
    assert [(c["id"], c["text"]) for c in snap["claims"]][-1] == (3, v2.claim(4).text)


@pytest.fixture
def v2_data():
    return yaml.safe_load(V2.read_text(encoding="utf-8"))


def _rules(data) -> set[str]:
    return {p.rule for p in validate(parse_case(data))}


def test_validator_checks_unlocks(v2_data):
    claims = {c["id"]: c for c in v2_data["claims"]}
    claims[4]["unlock"]["examples"] = ["只有一句"]
    assert "unlock-examples" in _rules(v2_data)
    claims[4]["unlock"]["examples"] = ["一", "二"]
    claims[3]["unlock"] = {"topic": "保险柜密码", "examples": ["一", "二"]}
    assert "unique-topics" in _rules(v2_data)
    claims[3]["unlock"] = {"after": 9}
    assert "refs-exist" in _rules(v2_data)
    claims[3]["unlock"] = {"after": 5}
    claims[5]["unlock"] = {"after": 3}
    assert "unlock-reachable" in _rules(v2_data)


def test_needs_an_opening_claim(v2_data):
    for c in v2_data["claims"]:
        c["unlock"] = {"after": 1}
    assert "has-opening" in _rules(v2_data)


def test_confession_text_comes_from_the_case(v2):
    from pozhan.director.suspect import task_confess

    x = v2.contradiction(3, 4)  # 密码那条也可能是最后一条
    task = task_confess(v2, x)
    assert v2.suspect.confession in task and x.concession not in task


def test_suspect_is_never_told_amended_claims_in_advance(v2):
    from pozhan.director.suspect import _system

    state = new_game(v2, 0)
    prompt = _system(v2, state, 0)
    assert v2.claim(3).text not in prompt and v2.claim(5).text not in prompt  # 没戳破之前不知道要改口成什么
    assert v2.claim(4).text in prompt  # 问到才说的那条要知道，好在被问到相关的事时含糊过去


def test_hint_when_every_spoken_claim_is_broken_but_some_are_unasked(v2):
    state = new_game(v2, 0)
    for move in [Present(2, 1), Present(6, 3), Present(4, 2), Present(5, 4)]:
        state, _ = apply(v2, state, move, 1)
    assert not state.over and set(state.broken) == set(state.revealed)
    hint = narrator.still_holding(v2, state)
    assert "追问" in hint and "证词五" not in hint


def test_classifier_only_offers_unbroken_claims(v2):
    state, _ = apply(v2, new_game(v2, 0), Present(card=2, claim=1), 1)
    system = build_messages(v2, "t", state)[0]["content"]
    assert v2.claim(1).text not in system
    assert f"2. {v2.claim(2).text}" in system and f"3. {v2.claim(3).text}" in system
