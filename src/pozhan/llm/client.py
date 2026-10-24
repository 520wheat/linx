from collections.abc import AsyncIterator
from typing import Protocol

Message = dict[str, str]  # {"role": ..., "content": ...}


class LLMError(Exception):
    pass


class LLM(Protocol):
    async def complete(self, model: str, messages: list[Message], *, timeout: float = 10.0) -> str:
        """一次性返回完整回复。"""
        ...

    def stream(self, model: str, messages: list[Message], *, timeout: float = 20.0) -> AsyncIterator[str]:
        """按增量返回回复文本。"""
        ...


class OpenAICompatLLM:
    """调用任意 OpenAI 兼容的 /chat/completions。实现见 #8 / #9。"""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def complete(self, model: str, messages: list[Message], *, timeout: float = 10.0) -> str:
        raise NotImplementedError

    async def stream(
        self, model: str, messages: list[Message], *, timeout: float = 20.0
    ) -> AsyncIterator[str]:
        raise NotImplementedError
        yield ""
