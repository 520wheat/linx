"""陪玩屏：随语音实时更新的只读大屏（Proposal #36）。

- snapshot  根据案件和会话生成屏幕快照，结局前不含任何剧透
- hub       保存每局的最新快照，推送给订阅的屏幕
- static/   陪玩屏页面（单个 HTML 文件）
"""

from pathlib import Path

from pozhan.screen.hub import ANY, ScreenHub
from pozhan.screen.snapshot import build_snapshot

PAGE = Path(__file__).with_name("static") / "index.html"

__all__ = ["ANY", "PAGE", "ScreenHub", "build_snapshot"]
