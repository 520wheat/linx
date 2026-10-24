"""设备模拟器：用软件冒充一台灵矽设备，端到端测试《破绽》（#11）。

用 macOS 的 say 合成玩家语音，Opus 编码后按 manual 模式（按键说话）上传；
记录平台下发的 stt / llm / tts 消息、每轮时延，可选把下行语音存成 WAV 方便试听。

依赖：macOS（say）、ffmpeg、libopus（brew install opus ffmpeg）。
用法：
  uv run --group devsim python tools/devsim.py ota          # 打印激活码；在智控台「设备管理 → 新增」填入
  uv run --group devsim python tools/devsim.py ota          # 绑定后再跑一次，保存连接信息
  uv run --group devsim python tools/devsim.py say 你好 "念一下证词"
  uv run --group devsim python tools/devsim.py play scripts/win.txt --audio out/
设备身份保存在 .data/devsim.json（已加入 .gitignore，含访问令牌，不要提交）。
"""

import argparse
import asyncio
import ctypes.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path

OTA_URL = "https://xrobo.qiniuapi.com/v1/ota/"
STATE = Path(os.environ.get("DEVSIM_STATE", ".data/devsim.json"))
VOICE = os.environ.get("DEVSIM_VOICE", "Tingting")  # 系统里能合成中文的语音；Flo 等语音可能只输出静音
RATE, FRAME_MS = 16000, 60
FRAME_SAMPLES = RATE * FRAME_MS // 1000
CLOSED_HINT = (
    "平台关闭了连接。常见原因：智能体用的是「我的模型」里的自定义模型，但该模型没填 API 密钥"
    "（平台初始化模型失败会在握手后立即断开）。"
)


def load_identity() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    mac = "02:" + ":".join(f"{random.randint(0, 255):02x}" for _ in range(5))  # 本地管理型 MAC
    ident = {"mac": mac, "client_id": str(uuid.uuid4())}
    save_identity(ident)
    return ident


def save_identity(ident: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(ident, indent=2))


def ota(ident: dict) -> None:
    body = {
        "application": {"version": "1.0.0", "elf_sha256": "0" * 64},
        "mac_address": ident["mac"],
        "uuid": ident["client_id"],
        "board": {"type": "pozhan-devsim", "ssid": "devsim", "rssi": -40},
    }
    req = urllib.request.Request(
        OTA_URL,
        data=json.dumps(body).encode(),
        headers={
            "Activation-Version": "1",
            "Device-Id": ident["mac"],
            "Client-Id": ident["client_id"],
            "User-Agent": "pozhan-devsim/0.1",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    if "activation" in data:
        print(
            f"激活码：{data['activation'].get('code')}  → 在智控台「设备管理 → 新增」填入，然后再运行一次 ota"
        )
        return
    ws = data.get("websocket") or {}
    if not ws.get("token"):
        print("设备未绑定，也没有拿到激活码：", json.dumps(data, ensure_ascii=False)[:300])
        return
    # OTA 可能返回明文 ws://，经过本机代理时连接会被当成普通 HTTP 掐断，统一改用 wss
    ident["ws_url"] = ws["url"].replace("ws://", "wss://", 1)
    ident["token"] = ws["token"]
    save_identity(ident)
    print(f"已绑定，连接信息已保存到 {STATE}")


def synth(text: str) -> bytes:
    """文本 → 16k 单声道 s16le PCM。"""
    with tempfile.TemporaryDirectory() as d:
        aiff = Path(d) / "a.aiff"
        subprocess.run(["say", "-v", VOICE, "-o", str(aiff), text], check=True)
        out = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                str(aiff),
                "-ac",
                "1",
                "-ar",
                str(RATE),
                "-f",
                "s16le",
                "-",
            ],
            check=True,
            capture_output=True,
        )
    if len(out.stdout) < RATE:  # 不到 0.5 秒，基本是语音不可用
        raise SystemExit(f"语音 {VOICE} 合成结果几乎为空，换一个：DEVSIM_VOICE=Tingting / Meijia")
    return out.stdout


@dataclass
class Turn:
    said: str
    stt: str = ""
    emotion: str = ""
    sentences: list[str] = field(default_factory=list)
    t_stt: float | None = None
    t_first_sentence: float | None = None
    t_first_audio: float | None = None
    t_done: float | None = None
    audio: bytearray = field(default_factory=bytearray)

    @property
    def reply(self) -> str:
        return "".join(self.sentences)


def _opus():
    if not ctypes.util.find_library("opus"):
        os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")
    import opuslib

    return opuslib


class Device:
    def __init__(self, ident: dict) -> None:
        if "token" not in ident:
            raise SystemExit("设备还没绑定：先运行 ota")
        self.ident = ident
        self.ws = None
        self.session_id = None
        self.queue: asyncio.Queue = asyncio.Queue()
        opuslib = _opus()
        self.encoder = opuslib.Encoder(RATE, 1, opuslib.APPLICATION_VOIP)
        self.decoder = None
        self.down_rate = RATE

    async def __aenter__(self):
        import websockets

        headers = {
            "Authorization": f"Bearer {self.ident['token']}",
            "Protocol-Version": "1",
            "Device-Id": self.ident["mac"],
            "Client-Id": self.ident["client_id"],
        }
        self.ws = await websockets.connect(
            self.ident["ws_url"], additional_headers=headers, max_size=None, ping_interval=None
        )
        await self.ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "version": 1,
                    "features": {"mcp": False},
                    "transport": "websocket",
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": RATE,
                        "channels": 1,
                        "frame_duration": FRAME_MS,
                    },
                }
            )
        )
        hello = json.loads(await asyncio.wait_for(self.ws.recv(), 10))
        self.session_id = hello.get("session_id")
        params = hello.get("audio_params") or {}
        self.down_rate = int(params.get("sample_rate", RATE))
        self.decoder = _opus().Decoder(self.down_rate, 1)
        self.reader = asyncio.create_task(self._read())
        return self

    async def __aexit__(self, *exc):
        self.reader.cancel()
        await self.ws.close()

    async def _read(self):
        try:
            async for msg in self.ws:
                await self.queue.put(msg)
        except Exception as e:  # 连接断开：交给 say() 报告
            await self.queue.put(e)

    async def say(self, text: str, timeout: float = 60) -> Turn:
        turn = Turn(said=text)
        pcm = synth(text)
        frame = FRAME_SAMPLES * 2
        pcm += b"\x00" * (-len(pcm) % frame) + b"\x00" * frame * 5  # 补齐一帧，再加 300ms 静音
        import websockets

        listen = {"session_id": self.session_id, "type": "listen", "mode": "manual"}
        try:
            await self.ws.send(json.dumps({**listen, "state": "start"}))
            for i in range(0, len(pcm), frame):
                await self.ws.send(self.encoder.encode(pcm[i : i + frame], FRAME_SAMPLES))
                await asyncio.sleep(FRAME_MS / 1000)
            await self.ws.send(json.dumps({**listen, "state": "stop"}))
        except websockets.ConnectionClosed as e:
            raise SystemExit(CLOSED_HINT + f"（{e!r}）") from None
        t0 = time.monotonic()  # 从「说完」开始计时

        deadline = t0 + timeout
        while time.monotonic() < deadline:
            try:
                msg = await asyncio.wait_for(self.queue.get(), deadline - time.monotonic())
            except TimeoutError:
                break
            if isinstance(msg, Exception):
                raise SystemExit(CLOSED_HINT + f"（{msg!r}）")
            now = time.monotonic() - t0
            if isinstance(msg, bytes):
                turn.t_first_audio = turn.t_first_audio or now
                try:
                    turn.audio += self.decoder.decode(msg, self.down_rate * FRAME_MS // 1000)
                except Exception:
                    pass
                continue
            m = json.loads(msg)
            kind, state = m.get("type"), m.get("state")
            if kind == "stt":
                turn.stt, turn.t_stt = m.get("text", ""), now
            elif kind == "llm" and not turn.emotion:
                turn.emotion = m.get("emotion", "")
            elif kind == "tts" and state == "sentence_start":
                turn.t_first_sentence = turn.t_first_sentence or now
                turn.sentences.append(m.get("text", ""))
            elif kind == "tts" and state == "stop":
                turn.t_done = now
                break
        return turn


def fmt(t: float | None) -> str:
    return f"{t:5.2f}s" if t is not None else "  -  "


def report(i: int, turn: Turn) -> None:
    print(f"\n#{i} 说：{turn.said}")
    print(f"   识别：{turn.stt or '（无）'}")
    print(f"   情绪：{turn.emotion or '（无）'}   回复：{turn.reply or '（无）'}")
    print(
        f"   时延（从说完起）：识别 {fmt(turn.t_stt)}  首句 {fmt(turn.t_first_sentence)}"
        f"  首个音频 {fmt(turn.t_first_audio)}  播完 {fmt(turn.t_done)}"
    )


def save_wav(path: Path, pcm: bytes, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


async def run(lines: list[str], audio_dir: Path | None) -> int:
    ident = load_identity()
    turns = []
    async with Device(ident) as dev:
        for i, text in enumerate(lines, 1):
            turn = await dev.say(text)
            report(i, turn)
            turns.append(turn)
            if audio_dir and turn.audio:
                save_wav(audio_dir / f"{i:02d}.wav", bytes(turn.audio), dev.down_rate)
    firsts = sorted(t.t_first_audio for t in turns if t.t_first_audio is not None)
    if firsts:
        print(
            f"\n共 {len(turns)} 轮，首个音频时延 p50 {firsts[len(firsts) // 2]:.2f}s，最大 {firsts[-1]:.2f}s"
        )
    return 0 if all(t.reply for t in turns) else 1


def main() -> None:
    p = argparse.ArgumentParser(prog="devsim")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ota", help="OTA 上报：未绑定时打印激活码，已绑定时保存连接信息")
    s = sub.add_parser("say", help="依次说几句话")
    s.add_argument("texts", nargs="+")
    s.add_argument("--audio", type=Path, help="把每轮下行语音存成 WAV")
    pl = sub.add_parser("play", help="按脚本文件（每行一句，# 开头为注释）完整打一局")
    pl.add_argument("script", type=Path)
    pl.add_argument("--audio", type=Path)
    args = p.parse_args()

    if args.cmd == "ota":
        ota(load_identity())
    elif args.cmd == "say":
        sys.exit(asyncio.run(run(args.texts, args.audio)))
    elif args.cmd == "play":
        lines = [ln.strip() for ln in args.script.read_text(encoding="utf-8").splitlines()]
        sys.exit(asyncio.run(run([ln for ln in lines if ln and not ln.startswith("#")], args.audio)))


if __name__ == "__main__":
    main()
