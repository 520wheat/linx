import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from pozhan.engine.state import Interrogation
from pozhan.llm.client import Message


@dataclass
class Session:
    key: str
    state: Interrogation | None = None
    last_reply: str = ""  # 「再说一遍」时复述
    updated_at: float = field(default_factory=time.time)


class SessionStore(Protocol):
    def get(self, key: str) -> Session | None: ...

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

    def put(self, session: Session) -> None:
        session.updated_at = self.clock()
        self._data[session.key] = session


class SessionKeyResolver(Protocol):
    def resolve(self, headers: Mapping[str, str], messages: list[Message]) -> str: ...


class HeaderResolver:
    """按顺序取第一个存在的请求头作为会话键。具体用哪些头，等平台请求格式验证后确定（#10）。"""

    def __init__(
        self, header_names: tuple[str, ...] = ("x-linx-device-id",), fallback: str = "default"
    ) -> None:
        self.header_names = header_names
        self.fallback = fallback

    def resolve(self, headers: Mapping[str, str], messages: list[Message]) -> str:
        lowered = {k.lower(): v for k, v in headers.items()}
        for name in self.header_names:
            if lowered.get(name):
                return lowered[name]
        return self.fallback
