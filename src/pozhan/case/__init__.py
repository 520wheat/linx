"""案件数据：一个案件由证词、线索卡、矛盾表和档位组成，规则引擎只依赖这里的定义。"""

from pozhan.case.loader import CaseFormatError, load_case, parse_case
from pozhan.case.model import Card, Case, Claim, Contradiction, Limits, Stage, Suspect
from pozhan.case.validator import Problem, validate

__all__ = [
    "Card",
    "Case",
    "CaseFormatError",
    "Claim",
    "Contradiction",
    "Limits",
    "Problem",
    "Stage",
    "Suspect",
    "load_case",
    "parse_case",
    "validate",
]
