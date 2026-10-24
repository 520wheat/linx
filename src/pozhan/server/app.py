import hmac
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from pozhan.game import Game
from pozhan.llm.client import Message
from pozhan.session.store import SessionKeyResolver

MODEL_ID = "pozhan"
log = logging.getLogger(__name__)


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


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "invalid_request_error"}}, status_code=status)


def create_app(
    game: Game,
    resolver: SessionKeyResolver,
    *,
    api_key: str = "",
    request_log: str | Path | None = None,
) -> FastAPI:
    """api_key 非空时要求 Authorization: Bearer <api_key>（即灵矽「我的模型」里填的 API 密钥）。

    request_log 非空时，把平台发来的请求（去掉鉴权头）逐行记下来，用于核对平台的请求格式。
    """
    app = FastAPI(title="pozhan")

    def authorized(request: Request) -> bool:
        if not api_key:
            return True
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        return hmac.compare_digest(given, api_key)

    def record(request: Request, body: dict) -> None:
        if not request_log:
            return
        headers = {k: v for k, v in request.headers.items() if k.lower() != "authorization"}
        path = Path(request_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"ts": time.time(), "headers": headers, "body": body}, ensure_ascii=False) + "\n"
            )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "case": game.case.id}

    @app.get("/v1/models")
    async def models(request: Request):
        if not authorized(request):
            return _error(401, "invalid api key")
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        if not authorized(request):
            return _error(401, "invalid api key")
        try:
            body = await request.json()
        except ValueError:
            return _error(400, "body must be JSON")
        record(request, body)
        messages: list[Message] = body.get("messages") or []
        key = resolver.resolve(request.headers, body)
        text = _last_user_text(messages)
        cid = "chatcmpl-" + uuid.uuid4().hex[:16]

        if not body.get("stream"):
            reply = "".join([part async for part in game.turn(key, text)])
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
            try:
                async for part in game.turn(key, text):
                    yield _chunk(cid, {"content": part})
            except Exception:  # 出错也要把流正常收尾，避免设备卡住
                log.exception("turn failed for %s", key)
                yield _chunk(cid, {"content": "😶刚才走神了，你能再说一遍吗？"})
            yield _chunk(cid, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
