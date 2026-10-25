from pathlib import Path

from pozhan.case.model import Case


def load_case(path: str | Path) -> Case:
    """从 YAML 文件加载案件。实现见 #6。"""
    raise NotImplementedError("load_case: 见 #6")
