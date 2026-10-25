"""骨架冒烟测试：请求能走过 server → game → intent → engine → director 整条主干。"""

import json

import httpx

from pozhan.cli import build_app
from tests.conftest import GOLDEN_WATCH


async def _post(payload: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=build_app(str(GOLDEN_WATCH)))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/chat/completions", json=payload)


async def test_non_stream_reply_starts_with_stage_emoji():
    r = await _post({"model": "pozhan", "messages": [{"role": "user", "content": "开始审讯"}]})
    assert r.status_code == 200
    content = r.json()["choices"][0]["message"]["content"]
    assert content.startswith("😌")


async def test_stream_reply_is_openai_sse():
    r = await _post({"model": "pozhan", "stream": True, "messages": [{"role": "user", "content": "你好"}]})
    lines = [line for line in r.text.splitlines() if line.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(line[6:]) for line in lines[:-1]]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text.startswith("😌")
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


async def test_models_endpoint():
    transport = httpx.ASGITransport(app=build_app(str(GOLDEN_WATCH)))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/models")
    assert r.json()["data"][0]["id"] == "pozhan"
