import asyncio
import hmac
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from pozhan.game import Game
from pozhan.llm.client import Message
from pozhan.screen import ANY, PAGE, ScreenHub, build_snapshot
from pozhan.session.store import SessionKeyResolver
from pozhan.voice import VoiceRelay

MODEL_ID = "pozhan"
MAX_BODY_BYTES = 1_000_000
MAX_TEXT_CHARS = 200  # 语音识别出来的一句话远小于这个长度；超长输入多半是滥用（#31）
log = logging.getLogger(__name__)


def _last_user_text(messages: list[Message]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content") or ""
            if isinstance(content, list):  # OpenAI 多段内容格式
                return "".join(p.get("text", "") for p in content if isinstance(p, dict))
            return content
    return ""


# 智能体开着「情绪识别」时，灵矽会在 ASR 结果末尾追加情绪标注，例如「开始审讯 [neutral的说]」（#33）
_ASR_EMOTION = re.compile(r"\s*\[([A-Za-z_]+)的说\]\s*$")


def split_emotion(text: str) -> tuple[str, str | None]:
    """去掉灵矽追加的情绪标注，返回 (玩家原话, 识别出的情绪)。"""
    m = _ASR_EMOTION.search(text)
    if not m:
        return text, None
    return text[: m.start()], m.group(1)


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
    screen: ScreenHub | None = None,
    screen_token: str = "",
    voice: VoiceRelay | None = None,
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

    def screen_allowed(request: Request) -> bool:
        if not screen_token:
            return True
        given = request.query_params.get("token") or request.headers.get("authorization", "").removeprefix(
            "Bearer "
        )
        return hmac.compare_digest(given.strip(), screen_token)

    def current_snapshot(device: str | None) -> dict:
        key = screen.resolve(device) if screen else None
        snap = (screen.latest(key) if screen else None) or build_snapshot(game.case, None, time.time())
        # hub 里存的是发布时刻的快照；前端用 serverNow 校准倒计时，所以这里换成当前时间
        return {**snap, "serverNow": time.time()}

    @app.get("/")
    async def root(request: Request):
        # 直接打开域名时进入网页开玩；带上原来的查询参数（token 等）
        query = request.url.query
        return RedirectResponse("/screen?" + (query if "play=" in query else "play=1&" + query).rstrip("&"))

    # 美术资源（#61）：嫌疑人立绘和案件封面，不含对局数据，不需要令牌
    app.mount("/screen/img", StaticFiles(directory=PAGE.parent / "img", check_dir=False), name="screen-img")

    @app.get("/screen")
    async def screen_page():
        # 页面本身不含对局数据，数据接口才校验令牌；页面从自己的 URL 里取 token 去请求数据
        return FileResponse(PAGE, media_type="text/html; charset=utf-8")

    @app.get("/screen/voice/status")
    async def voice_status(request: Request):
        if not screen_allowed(request):
            return _error(401, "invalid screen token")
        if voice is None:
            return {"enabled": False}
        return {"enabled": True, "busy": voice.busy.locked(), "device": voice.device.mac}

    @app.websocket("/screen/voice")
    async def voice_ws(ws: WebSocket):
        # 网页开玩（#43）：网页充当灵矽设备，令牌沿用陪玩屏的只读令牌
        given = ws.query_params.get("token") or ""
        if screen_token and not hmac.compare_digest(given, screen_token):
            await ws.close(code=4401)
            return
        await ws.accept()
        if voice is None:
            await ws.send_json({"type": "error", "message": "服务端没有配置网页开玩用的灵矽设备"})
            await ws.close(code=4404)
            return
        await voice.serve(ws)

    @app.get("/screen/state")
    async def screen_state(request: Request):
        if not screen_allowed(request):
            return _error(401, "invalid screen token")
        return current_snapshot(request.query_params.get("device"))

    @app.get("/screen/events")
    async def screen_events(request: Request):
        if not screen_allowed(request):
            return _error(401, "invalid screen token")
        if screen is None:
            return _error(404, "screen disabled")
        device = request.query_params.get("device")
        channel = (screen.resolve(device) or device) if device else ANY

        async def events() -> AsyncIterator[str]:
            # 先发约 2KB 的注释：有些代理和隧道会把很小的数据块攒在缓冲里不往下发
            yield ":" + " " * 2048 + "\n\n"
            yield f"data: {json.dumps(current_snapshot(device), ensure_ascii=False)}\n\n"
            queue = screen.subscribe(channel)
            try:
                while True:
                    try:
                        snap = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keepalive\n\n"  # 让反向代理和隧道不因空闲断开连接
                        continue
                    yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
            finally:
                screen.unsubscribe(channel, queue)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "case": game.case.id, "cases": [c.id for c in game.cases]}

    @app.get("/v1/models")
    async def models(request: Request):
        if not authorized(request):
            return _error(401, "invalid api key")
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        if not authorized(request):
            return _error(401, "invalid api key")
        if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
            return _error(413, "request body too large")
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            return _error(413, "request body too large")
        try:
            body = json.loads(raw)
        except ValueError:
            return _error(400, "body must be JSON")
        if not isinstance(body, dict):
            return _error(400, "body must be a JSON object")
        record(request, body)
        messages: list[Message] = body.get("messages") or []
        key = resolver.resolve(request.headers, body)
        text, voice_emotion = split_emotion(_last_user_text(messages))
        if len(text) > MAX_TEXT_CHARS:
            log.warning("user text truncated from %d chars for %s", len(text), key)
            text = text[:MAX_TEXT_CHARS]
        cid = "chatcmpl-" + uuid.uuid4().hex[:16]

        if not body.get("stream"):
            reply = "".join([part async for part in game.turn(key, text, voice_emotion=voice_emotion)])
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
                async for part in game.turn(key, text, voice_emotion=voice_emotion):
                    yield _chunk(cid, {"content": part})
            except Exception:  # 出错也要把流正常收尾，避免设备卡住
                log.exception("turn failed for %s", key)
                yield _chunk(cid, {"content": "😶刚才走神了，你能再说一遍吗？"})
            yield _chunk(cid, {}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app
