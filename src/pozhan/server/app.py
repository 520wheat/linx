import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from pozhan.game import Game
from pozhan.llm.client import Message
from pozhan.session.store import SessionKeyResolver

MODEL_ID = "pozhan"


def _last_user_text(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content") or ""
            if isinstance(content, list):  # OpenAI 多段内容格式
                return "".join(p.get("text", "") for p in content if isinstance(p, dict))
            return content
    return ""


def _chunk(cid: str, delta: dict, finish: str | None = None) -> str:
    body = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def create_app(game: Game, resolver: SessionKeyResolver) -> FastAPI:
    app = FastAPI(title="pozhan")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True}

    @app.get("/v1/models")
    async def models() -> dict:
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        messages: list[Message] = body.get("messages") or []
        key = resolver.resolve(request.headers, messages)
        text = _last_user_text(messages)
        cid = "chatcmpl-" + uuid.uuid4().hex[:16]

        if not body.get("stream"):
            reply = "".join([part async for part in game.turn(key, text, messages)])
            return JSONResponse(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": MODEL_ID,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": reply},
                            "finish_reason": "stop",
                        }
                    ],
                }
            )

        async def events() -> AsyncIterator[str]:
            yield _chunk(cid, {"role": "assistant"})
            async for part in game.turn(key, text, messages):
                yield _chunk(cid, {"content": part})
            yield _chunk(cid, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
