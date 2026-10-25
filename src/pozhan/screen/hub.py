"""屏幕快照的发布与订阅：按会话保存最新快照，推送给正在看的陪玩屏（#38）。"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

ANY = "*"  # 不指定设备时订阅这个频道：跟随最近活跃的一局


class ScreenHub:
    def __init__(self) -> None:
        self._latest: dict[str, dict[str, Any]] = {}
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self.last_key: str | None = None

    def resolve(self, device: str | None) -> str | None:
        """把查询参数里的设备号对应到会话键；不指定时取最近活跃的一局。"""
        if not device:
            return self.last_key
        for key in self._latest:
            if key == device or key.endswith(":" + device):
                return key
        return None

    def latest(self, key: str | None) -> dict[str, Any] | None:
        return self._latest.get(key) if key else None

    def publish(self, key: str, snapshot: dict[str, Any]) -> None:
        self._latest[key] = snapshot
        self.last_key = key
        for channel in (key, ANY):
            for q in self._subs.get(channel, ()):
                if q.full():  # 屏幕跟不上时丢掉旧快照，只保留最新的
                    q.get_nowait()
                q.put_nowait(snapshot)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subs.setdefault(channel, set()).add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs[channel].discard(q)
