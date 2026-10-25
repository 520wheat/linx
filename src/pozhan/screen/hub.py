"""屏幕快照的发布与订阅：按会话保存最新快照，推送给正在看的陪玩屏（#38）。"""

import asyncio
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
        for channel, queues in self._subs.items():
            # 频道可以是完整会话键、设备号（屏幕先于设备连上时只知道设备号）或 ANY
            if channel not in (key, ANY) and not key.endswith(":" + channel):
                continue
            for q in queues:
                if q.full():  # 屏幕跟不上时丢掉旧快照，只保留最新的
                    q.get_nowait()
                q.put_nowait(snapshot)

    # 订阅直接交出队列，而不是异步生成器：调用方要给 get() 加超时发 keepalive，
    # 超时取消一个生成器的 anext() 会把生成器一起关掉
    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subs.setdefault(channel, set()).add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        self._subs.get(channel, set()).discard(q)
