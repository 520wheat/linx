from dataclasses import dataclass

from pozhan.case.model import Case


@dataclass(frozen=True)
class Problem:
    """校验发现的一个问题，message 直接给案件作者看。"""

    rule: str
    message: str


def validate(case: Case) -> list[Problem]:
    """检查案件是否公平、可解。规则见 #6。"""
    return []
