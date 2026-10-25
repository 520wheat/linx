from pathlib import Path

import pytest
import yaml

from pozhan.case import Case, load_case

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_WATCH = ROOT / "cases" / "golden-watch.yaml"


@pytest.fixture
def case() -> Case:
    return load_case(GOLDEN_WATCH)


@pytest.fixture
def case_data() -> dict:
    """案件的原始 YAML 数据，用来构造各种反例。"""
    return yaml.safe_load(GOLDEN_WATCH.read_text(encoding="utf-8"))
