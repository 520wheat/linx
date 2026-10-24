from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    INTERROGATING = "interrogating"
    CONFESSED = "confessed"  # 胜利
    LAWYER = "lawyer"  # 失败
    QUIT = "quit"  # 玩家主动结束


@dataclass(frozen=True)
class Interrogation:
    """一局审讯的全部状态。不可变，规则引擎每次返回新状态。"""

    case_id: str
    started_at: float
    phase: Phase = Phase.INTERROGATING
    stage: int = 0  # 当前档位下标
    broken: tuple[int, ...] = ()  # 已戳破的证词编号，按戳破顺序
    strikes: int = 0  # 出示错误次数
    idle: int = 0  # 距上次进展的提问数

    @property
    def over(self) -> bool:
        return self.phase is not Phase.INTERROGATING
