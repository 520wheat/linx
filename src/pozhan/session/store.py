import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pozhan.engine.state import Interrogation
from pozhan.llm.client import Message

HISTORY_TURNS = 8


@dataclass
class Session:
    key: str
    state: Interrogation | None = None
    game_id: str = ""
    last_reply: str = ""  # 「再说一遍」时原样复述
    history: list[Message] = field(default_factory=list)  # 服务端自己保存对话，不依赖平台传来的历史
    updated_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    # 陪玩屏展示用（#38）：最近一次关键事件、最近一句台词、对局结束时间
    event: dict[str, Any] | None = None
    event_seq: int = 0
    line: dict[str, str] | None = None
    ended_at: float | None = None

    def remember(self, user: str, assistant: str) -> None:
        self.history += [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
        del self.history[: -HISTORY_TURNS * 2]


class SessionStore(Protocol):
    def get(self, key: str) -> Session | None: ...

    def get_or_create(self, key: str) -> Session: ...

    def put(self, session: Session) -> None: ...


class MemoryStore:
    """进程内存储，过期自动丢弃。多实例部署时换成 Redis 实现（不在本期）。"""

    def __init__(self, ttl_seconds: float = 3600, clock=time.time) -> None:
        self.ttl = ttl_seconds
        self.clock = clock
        self._data: dict[str, Session] = {}

    def get(self, key: str) -> Session | None:
        s = self._data.get(key)
        if s is None or self.clock() - s.updated_at > self.ttl:
            self._data.pop(key, None)
            return None
        return s

    def get_or_create(self, key: str) -> Session:
        s = self.get(key)
        if s is None:
            s = Session(key=key, updated_at=self.clock())
            self._data[key] = s
        return s

    def put(self, session: Session) -> None:
        session.updated_at = self.clock()
        self._data[session.key] = session


class SessionKeyResolver(Protocol):
    def resolve(self, headers: Mapping[str, str], body: Mapping[str, Any]) -> str: ...


# 灵矽调用云端 MCP 时会带 X-Linx-Device-Id / X-Linx-Session-Id；「我的模型」请求是否带，以实测为准（#10）
DEFAULT_HEADERS = ("x-linx-device-id", "x-linx-session-id", "x-device-id", "device-id")


class HeaderResolver:
    """会话键的来源依次为：设备 / 会话请求头 → 请求体的 user 字段 → 固定值（每个部署只有一局）。"""

    def __init__(self, header_names: tuple[str, ...] = DEFAULT_HEADERS, fallback: str = "default") -> None:
        self.header_names = header_names
        self.fallback = fallback

    def resolve(self, headers: Mapping[str, str], body: Mapping[str, Any]) -> str:
        lowered = {k.lower(): v for k, v in headers.items()}
        for name in self.header_names:
            if lowered.get(name):
                return f"{name}:{lowered[name]}"
        user = body.get("user")
        if isinstance(user, str) and user:
            return f"user:{user}"
        return self.fallback
