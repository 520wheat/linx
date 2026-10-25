"""对局日志：每局一个 JSONL 文件，用于复盘和抽检（Proposal #3 验收标准 8）。"""

import json
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {"type": type(value).__name__, **asdict(value)}
    return value


class GameLog:
    def __init__(self, directory: str | Path | None) -> None:
        self.directory = Path(directory) if directory else None

    def write(self, session_key: str, game_id: str, **record: Any) -> None:
        if self.directory is None:
            return
        day = time.strftime("%Y-%m-%d")
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in session_key)[:80]
        path = self.directory / day / f"{safe}-{game_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), **{k: _plain(v) for k, v in record.items()}}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
