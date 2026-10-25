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
    # 已经说出口的证词编号，按说出口的顺序（#46）。玩家听到的「证词 N」是这里的第 N 条，不是案件文件里的编号
    revealed: tuple[int, ...] = ()

    def label(self, claim_id: int) -> int | None:
        """案件里的证词编号 → 玩家口中的证词序号。"""
        return self.revealed.index(claim_id) + 1 if claim_id in self.revealed else None

    def claim_at(self, label: int) -> int | None:
        """玩家口中的证词序号 → 案件里的证词编号；还没说出口的序号返回 None。"""
        return self.revealed[label - 1] if 1 <= label <= len(self.revealed) else None

    @property
    def over(self) -> bool:
        return self.phase is not Phase.INTERROGATING
