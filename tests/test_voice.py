"""网页开玩的灵矽中转（#43）：用假的灵矽服务端核对协议，不连真实平台。"""

import asyncio
import json

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pozhan.case import load_case
from pozhan.director import Director
from pozhan.game import Game
from pozhan.intent import Interpreter, RuleMatcher
from pozhan.screen import ScreenHub
from pozhan.server import create_app
from pozhan.session import HeaderResolver, MemoryStore
from pozhan.voice import LinxDevice, VoiceRelay
from pozhan.voice.relay import UP_FRAME_BYTES, _opus
from tests.conftest import GOLDEN_WATCH

DEVICE = LinxDevice(mac="02:00:00:00:00:01", client_id="c-1", token="t", ws_url="wss://linx.test/v1/ws/")
DOWN_RATE = 24000


class FakeLinx:
    """按灵矽设备协议应答：握手回 hello，收到 listen stop 就回一句识别结果和一句语音。"""

    def __init__(self) -> None:
        self.sent: list = []
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.closed = False
        encoder = _opus().Encoder(DOWN_RATE, 1, _opus().APPLICATION_AUDIO)
        self.reply = encoder.encode(b"\x00\x01" * (DOWN_RATE * 60 // 1000), DOWN_RATE * 60 // 1000)

    async def send(self, msg) -> None:
        self.sent.append(msg)
        if isinstance(msg, bytes):
            return
        data = json.loads(msg)
        if data["type"] == "hello":
            hello = {"type": "hello", "session_id": "s-1", "audio_params": {"sample_rate": DOWN_RATE}}
            self.inbox.put_nowait(json.dumps(hello))
        elif data["type"] == "listen" and data["state"] == "stop":
            for m in (
                {"type": "stt", "text": "开始审讯 [neutral的说]"},
                {"type": "tts", "state": "start"},
                {"type": "mcp", "payload": {}},  # 网页用不上的消息不转发
            ):
                self.inbox.put_nowait(json.dumps(m, ensure_ascii=False))
            self.inbox.put_nowait(self.reply)
            self.inbox.put_nowait(json.dumps({"type": "tts", "state": "stop"}))

    async def recv(self):
        return await self.inbox.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self.inbox.get()
        if msg is None:
            raise StopAsyncIteration
        return msg

    async def close(self) -> None:
        self.closed = True
        self.inbox.put_nowait(None)


def make(voice: VoiceRelay | None, token: str = "") -> TestClient:
    case = load_case(GOLDEN_WATCH)
    hub = ScreenHub()
    game = Game(
        case=case,
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
        screen=hub,
    )
    return TestClient(create_app(game, HeaderResolver(), screen=hub, screen_token=token, voice=voice))


@pytest.fixture
def linx():
    made: list[FakeLinx] = []

    async def connect(device):
        assert device is DEVICE
        made.append(FakeLinx())
        return made[-1]

    return VoiceRelay(DEVICE, connect=connect), made


def test_relays_one_utterance_both_ways(linx):
    relay, made = linx
    with make(relay) as client, client.websocket_connect("/screen/voice") as ws:
        assert ws.receive_json() == {"type": "ready", "sampleRate": DOWN_RATE, "device": DEVICE.mac}
        ws.send_json({"type": "start"})
        ws.send_bytes(b"\x01\x00" * (UP_FRAME_BYTES // 2) + b"\x00\x00" * 100)  # 一帧半
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "stt"
        assert ws.receive_json() == {"type": "tts", "state": "start"}
        pcm = ws.receive_bytes()
        assert len(pcm) == DOWN_RATE * 60 // 1000 * 2
        assert ws.receive_json() == {"type": "tts", "state": "stop"}

    linx_side = made[0]
    texts = [json.loads(m) for m in linx_side.sent if isinstance(m, str)]
    assert texts[0]["type"] == "hello" and texts[0]["audio_params"]["format"] == "opus"
    assert texts[1] == {"session_id": "s-1", "type": "listen", "mode": "manual", "state": "start"}
    assert texts[-1] == {"session_id": "s-1", "type": "listen", "mode": "manual", "state": "stop"}
    frames = [m for m in linx_side.sent if isinstance(m, bytes)]
    assert len(frames) == 2 + 5  # 不足一帧的尾巴补零成一帧，再加 300ms 静音
    assert linx_side.closed


def test_talking_over_the_suspect_aborts_its_speech(linx):
    relay, made = linx
    with make(relay) as client, client.websocket_connect("/screen/voice") as ws:
        ws.receive_json()
        made[0].inbox.put_nowait(json.dumps({"type": "tts", "state": "start"}))
        assert ws.receive_json() == {"type": "tts", "state": "start"}
        ws.send_json({"type": "start"})  # 嫌疑人还在说，玩家按下了说话键
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["type"] == "stt"
    texts = [json.loads(m) for m in made[0].sent if isinstance(m, str)]
    assert texts[1] == {"session_id": "s-1", "type": "abort"}
    assert texts[2]["state"] == "start"


def test_only_one_web_player_at_a_time(linx):
    relay, _ = linx
    with make(relay) as client, client.websocket_connect("/screen/voice") as first:
        first.receive_json()
        assert client.get("/screen/voice/status").json()["busy"] is True
        with client.websocket_connect("/screen/voice") as second:
            assert second.receive_json() == {"type": "busy"}
            with pytest.raises(WebSocketDisconnect) as e:
                second.receive_json()
            assert e.value.code == 4409


def test_voice_requires_the_screen_token(linx):
    relay, _ = linx
    with make(relay, token="s3cret") as client:
        with pytest.raises(WebSocketDisconnect) as e, client.websocket_connect("/screen/voice") as ws:
            ws.receive_json()
        assert e.value.code == 4401
        assert client.get("/screen/voice/status").status_code == 401
        with client.websocket_connect("/screen/voice?token=s3cret") as ws:
            assert ws.receive_json()["type"] == "ready"


def test_voice_disabled_without_a_device():
    with make(None) as client:
        assert client.get("/screen/voice/status").json() == {"enabled": False}
        with client.websocket_connect("/screen/voice") as ws:
            assert ws.receive_json()["type"] == "error"


def test_linx_unreachable_is_reported():
    async def connect(device):
        raise OSError("no route")

    with make(VoiceRelay(DEVICE, connect=connect)) as client, client.websocket_connect("/screen/voice") as ws:
        assert ws.receive_json() == {"type": "error", "message": "连接灵矽失败"}


def test_device_file_upgrades_plain_ws(tmp_path):
    path = tmp_path / "devsim.json"
    path.write_text(json.dumps({"mac": "m", "client_id": "c", "token": "t", "ws_url": "ws://x/v1/ws/"}))
    assert LinxDevice.load(path).ws_url == "wss://x/v1/ws/"


def test_typed_text_and_taps_go_to_linx_as_detect(linx):
    # 点按操作和打字（#59）：灵矽把 detect 带的文字当作玩家的话
    relay, made = linx
    with make(relay) as client, client.websocket_connect("/screen/voice") as ws:
        ws.receive_json()
        ws.send_json({"type": "text", "text": "  用二号卡反驳证词一  "})
        ws.send_json({"type": "text", "text": "问" * 300})
        ws.send_json({"type": "text", "text": "   "})
        ws.send_json({"type": "start", "mode": "auto"})
        ws.send_json({"type": "stop"})
        ws.receive_json()
    texts = [json.loads(m) for m in made[0].sent if isinstance(m, str)]
    detect = [t for t in texts if t.get("state") == "detect"]
    assert detect[0] == {
        "session_id": "s-1",
        "type": "listen",
        "state": "detect",
        "text": "用二号卡反驳证词一",
    }
    assert len(detect[1]["text"]) == 100 and len(detect) == 2
    assert {"session_id": "s-1", "type": "listen", "mode": "auto", "state": "start"} in texts
    assert texts[-1] == {"session_id": "s-1", "type": "listen", "mode": "auto", "state": "stop"}


def test_unknown_listen_mode_falls_back_to_manual(linx):
    relay, made = linx
    with make(relay) as client, client.websocket_connect("/screen/voice") as ws:
        ws.receive_json()
        ws.send_json({"type": "start", "mode": "realtime"})
        ws.send_json({"type": "stop"})
        ws.receive_json()
    starts = [json.loads(m) for m in made[0].sent if isinstance(m, str) and '"start"' in m and "listen" in m]
    assert starts[0]["mode"] == "manual"
