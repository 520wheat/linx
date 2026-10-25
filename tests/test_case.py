import pytest

from pozhan.case import CaseFormatError, parse_case, validate


def rules(data: dict) -> set[str]:
    return {p.rule for p in validate(parse_case(data))}


def test_golden_watch_is_valid(case):
    assert validate(case) == []
    assert [c.id for c in case.claims] == [1, 2, 3]
    assert case.contradiction(2, 1) is not None
    assert case.contradiction(1, 1) is None
    assert case.stages[0].emoji == "😌"


def test_duplicate_ids(case_data):
    case_data["cards"].append(dict(case_data["cards"][0]))
    assert "unique-ids" in rules(case_data)


def test_contradiction_refers_to_missing_card(case_data):
    case_data["contradictions"][0]["card"] = 99
    assert "refs-exist" in rules(case_data)


def test_lie_without_breaker(case_data):
    case_data["contradictions"] = case_data["contradictions"][1:]
    case_data["stages"] = case_data["stages"][1:]
    assert "one-breaker-per-lie" in rules(case_data)


def test_lie_with_two_breakers(case_data):
    case_data["contradictions"].append(dict(case_data["contradictions"][0], card=1))
    assert "one-breaker-per-lie" in rules(case_data)


def test_truth_must_not_be_breakable(case_data):
    case_data["claims"][0]["lie"] = False
    assert "truths-unbreakable" in rules(case_data)


def test_needs_a_lie(case_data):
    for c in case_data["claims"]:
        c["lie"] = False
    case_data["contradictions"] = []
    case_data["stages"] = case_data["stages"][:1]
    assert "has-lies" in rules(case_data)


def test_needs_a_distractor(case_data):
    case_data["cards"] = [c for c in case_data["cards"] if c["id"] != 1]
    assert "has-distractor" in rules(case_data)


def test_stage_count(case_data):
    case_data["stages"] = case_data["stages"][:1]
    assert "stage-count" in rules(case_data)
    case_data["stages"] = case_data["stages"] * 5
    assert "stage-count" in rules(case_data)


def test_slip_every_positive(case_data):
    case_data["stages"][0]["slip_every"] = 0
    assert "slip-every" in rules(case_data)


def test_needs_slip_hint(case_data):
    case_data["contradictions"][0]["slip"] = ""
    assert "has-slip" in rules(case_data)


def test_limits_positive(case_data):
    case_data["limits"]["strikes"] = 0
    assert "limits" in rules(case_data)


def test_missing_field_is_reported(case_data):
    del case_data["suspect"]["name"]
    with pytest.raises(CaseFormatError, match="name"):
        parse_case(case_data)


def test_folded_yaml_spaces_between_chinese_sentences_are_removed(case):
    assert "。 " not in case.briefing and "不见了。监控显示" in case.briefing
    assert "KTV 包厢" in case.briefing  # 中英文之间的空格保留


def test_timeline_is_loaded(case):
    assert [s.time for s in case.timeline] == ["21:20", "21:32", "", "", "21:55"]
    assert [s.card for s in case.timeline] == [None, 2, 3, 4, None]


def test_timeline_card_must_exist(case_data):
    case_data["timeline"][1]["card"] = 9
    assert "refs-exist" in rules(case_data)


def test_timeline_is_optional(case_data):
    del case_data["timeline"]
    assert parse_case(case_data).timeline == ()
