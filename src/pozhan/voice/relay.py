import asyncio
import contextlib
import ctypes.util
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

UP_RATE, FRAME_MS = 16000, 60
UP_FRAME_BYTES = UP_RATE * FRAME_MS // 1000 * 2  # 60ms 的 16k 单声道 s16le
# 灵矽下发的文字消息里，网页用得上的几类：识别结果、TTS 开始/每句/结束
FORWARD_TYPES = {"stt", "tts", "llm"}


@dataclass(frozen=True)
class LinxDevice:
    """一台已绑定到智能体的灵矽设备身份。文件格式与 tools/devsim.py 生成的 .data/devsim.json 相同。"""

    mac: str
    client_id: str
    token: str
    ws_url: str

    @classmethod
    def load(cls, path: str | Path) -> "LinxDevice":
        data = json.loads(Path(path).read_text())
        # OTA 可能返回明文 ws://，经过本机代理时连接会被当成普通 HTTP 掐断
        return cls(
            data["mac"], data["client_id"], data["token"], data["ws_url"].replace("ws://", "wss://", 1)
        )


def _opus():
    # macOS 上 Homebrew 装的 libopus 不在 ctypes 的默认搜索路径里
    if not ctypes.util.find_library("opus"):
        os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")
    import opuslib

    return opuslib


async def _connect_linx(device: LinxDevice):
    import websockets

    return await websockets.connect(
        device.ws_url,
        additional_headers={
            "Authorization": f"Bearer {device.token}",
            "Protocol-Version": "1",
            "Device-Id": device.mac,
            "Client-Id": device.client_id,
        },
        max_size=None,
        ping_interval=None,
    )


class VoiceRelay:
    """把一个网页连接中转成一次灵矽设备会话。同一台设备同一时间只服务一个网页。"""

    def __init__(self, device: LinxDevice, connect: Callable[[LinxDevice], Any] = _connect_linx) -> None:
        self.device = device
        self.connect = connect
        self.busy = asyncio.Lock()

    async def serve(self, browser: WebSocket) -> None:
        if self.busy.locked():
            await browser.send_json({"type": "busy"})
            await browser.close(code=4409)
            return
        async with self.busy:
            try:
                upstream = await self.connect(self.device)
            except Exception as e:  # 灵矽连不上：告诉网页，不让它一直等
                log.warning("linx connect failed: %r", e)
                await browser.send_json({"type": "error", "message": "连接灵矽失败"})
                await browser.close(code=1011)
                return
            try:
                await self._relay(browser, upstream)
            finally:
                await upstream.close()

    async def _relay(self, browser: WebSocket, upstream) -> None:
        opuslib = _opus()
        await upstream.send(
            json.dumps(
                {
                    "type": "hello",
                    "version": 1,
                    "features": {"mcp": False},
                    "transport": "websocket",
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": UP_RATE,
                        "channels": 1,
                        "frame_duration": FRAME_MS,
                    },
                }
            )
        )
        hello = json.loads(await asyncio.wait_for(upstream.recv(), 10))
        session_id = hello.get("session_id")
        params = hello.get("audio_params") or {}
        down_rate = int(params.get("sample_rate", UP_RATE))
        encoder = opuslib.Encoder(UP_RATE, 1, opuslib.APPLICATION_VOIP)
        decoder = opuslib.Decoder(down_rate, 1)
        await browser.send_json({"type": "ready", "sampleRate": down_rate, "device": self.device.mac})

        listen = {"session_id": session_id, "type": "listen", "mode": "manual"}
        pending = bytearray()
        speaking = False  # 灵矽正在下发语音；玩家此时开口就先打断它

        async def send_frames(final: bool) -> None:
            if final and pending:
                pending.extend(b"\x00" * (-len(pending) % UP_FRAME_BYTES))
            while len(pending) >= UP_FRAME_BYTES:
                frame = bytes(pending[:UP_FRAME_BYTES])
                del pending[:UP_FRAME_BYTES]
                await upstream.send(encoder.encode(frame, UP_FRAME_BYTES // 2))

        async def from_browser() -> None:
            while True:
                msg = await browser.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                if msg.get("bytes"):
                    pending.extend(msg["bytes"])
                    await send_frames(final=False)
                elif msg.get("text"):
                    kind = json.loads(msg["text"]).get("type")
                    if kind == "start":
                        pending.clear()
                        if speaking:
                            await upstream.send(json.dumps({"session_id": session_id, "type": "abort"}))
                        await upstream.send(json.dumps({**listen, "state": "start"}))
                    elif kind == "stop":
                        await send_frames(final=True)
                        silence = encoder.encode(b"\x00" * UP_FRAME_BYTES, UP_FRAME_BYTES // 2)
                        for _ in range(5):  # 300ms 静音收尾，帮助识别断句
                            await upstream.send(silence)
                        await upstream.send(json.dumps({**listen, "state": "stop"}))

        async def from_linx() -> None:
            nonlocal speaking
            max_samples = down_rate * 120 // 1000
            async for msg in upstream:
                if isinstance(msg, bytes):
                    try:
                        await browser.send_bytes(decoder.decode(msg, max_samples))
                    except opuslib.OpusError:
                        continue
                    continue
                data = json.loads(msg)
                if data.get("type") == "tts" and data.get("state") in ("start", "stop"):
                    speaking = data["state"] == "start"
                if data.get("type") in FORWARD_TYPES:
                    await browser.send_text(msg)

        tasks = [asyncio.create_task(from_browser()), asyncio.create_task(from_linx())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                    await t
