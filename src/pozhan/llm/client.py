import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

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
    """调用任意 OpenAI 兼容的 /chat/completions。"""

    def __init__(
        self, base_url: str, api_key: str, *, temperature: float = 0.0, extra_body: dict | None = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.temperature = temperature
        self.extra_body = extra_body or {}  # 例如关闭思考：{"thinking": {"type": "disabled"}}
        self._client = httpx.AsyncClient(headers={"Authorization": f"Bearer {api_key}"})

    def _body(self, model: str, messages: list[Message], stream: bool) -> dict:
        return {
            **self.extra_body,
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }

    async def complete(self, model: str, messages: list[Message], *, timeout: float = 10.0) -> str:
        try:
            r = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=self._body(model, messages, stream=False),
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"].get("content") or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"{model}: {e!r}") from e

    async def stream(
        self, model: str, messages: list[Message], *, timeout: float = 20.0
    ) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=self._body(model, messages, stream=True),
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    choices = json.loads(data).get("choices") or []
                    delta = (choices[0].get("delta") or {}).get("content") if choices else None
                    if delta:
                        yield delta
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"{model}: {e!r}") from e

    async def aclose(self) -> None:
        await self._client.aclose()
