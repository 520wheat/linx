from pathlib import Path

import pytest
import yaml

from pozhan.case import Case, load_case

ROOT = Path(__file__).resolve().parent.parent
# 单元测试固定用第一版案件（三条开场证词、没有隐藏证词），案件内容改版不影响规则测试；
# 追问解锁（#46）用 HIDDEN 这份最小案件单独测
GOLDEN_WATCH = ROOT / "tests" / "fixtures" / "golden-watch-v1.yaml"
CASES = sorted((ROOT / "cases").glob("*.yaml"))


@pytest.fixture
def case() -> Case:
    return load_case(GOLDEN_WATCH)


@pytest.fixture
def case_data() -> dict:
    """案件的原始 YAML 数据，用来构造各种反例。"""
    return yaml.safe_load(GOLDEN_WATCH.read_text(encoding="utf-8"))
