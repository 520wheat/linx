"""接入层测试：用 OpenAI 兼容请求模拟灵矽，完整打一局胜利局和失败局。"""

import json

import httpx
import pytest

from pozhan.cli import build_app
from pozhan.config import Settings
from pozhan.director import Director
from pozhan.game import Game
from pozhan.gamelog import GameLog
from pozhan.intent import Interpreter, RuleMatcher
from pozhan.server import create_app
from pozhan.session import HeaderResolver, MemoryStore
from tests.conftest import GOLDEN_WATCH


class Client:
    def __init__(self, app, headers=None):
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
        self.headers = headers or {}
        self.messages = []

    async def say(self, text: str, *, stream: bool = True, headers=None) -> str:
        self.messages.append({"role": "user", "content": text})
        r = await self.http.post(
            "/v1/chat/completions",
            json={"model": "pozhan", "stream": stream, "messages": self.messages},
            headers={**self.headers, **(headers or {})},
        )
        assert r.status_code == 200, r.text
        if stream:
            lines = [ln[6:] for ln in r.text.splitlines() if ln.startswith("data: ")]
            assert lines[-1] == "[DONE]"
            reply = "".join(json.loads(x)["choices"][0]["delta"].get("content", "") for x in lines[:-1])
        else:
            reply = r.json()["choices"][0]["message"]["content"]
        self.messages.append({"role": "assistant", "content": reply})
        return reply


def make_app(tmp_path=None, api_key=""):
    game = Game(
        case=__import__("pozhan.case", fromlist=["load_case"]).load_case(GOLDEN_WATCH),
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
        log=GameLog(tmp_path),
    )
    return create_app(
        game, HeaderResolver(), api_key=api_key, request_log=tmp_path / "req.jsonl" if tmp_path else None
    )


async def test_build_app_from_settings():
    app = build_app(Settings(case_path=str(GOLDEN_WATCH), log_dir=""))
    reply = await Client(app).say("你好")
    assert reply.startswith("😌") and "年会" in reply


async def test_full_winning_game_over_http(tmp_path):
    c = Client(make_app(tmp_path))
    first = await c.say("你好小智", stream=False)  # 任何第一句话都会开局
    assert first.startswith("😌") and "九点到十点" in first and "规则" in first

    assert (await c.say("念一下证词")).startswith("😶")
    assert "电梯监控截图" in await c.say("念一下2号卡")
    wrong = await c.say("用1号卡反驳证词1")
    assert wrong.startswith("😌") and "律师还有二次就到" in wrong
    broke = await c.say("用2号卡反驳证词1")
    assert broke.startswith("😠") and "证词一被戳破" in broke
    assert (await c.say("三号卡反驳第二条证词")).startswith("😲")
    final = await c.say("4号卡反驳证词3")
    assert final.startswith("😭") and "案件告破" in final
    assert "结束" in await c.say("你还有什么要说的")

    logs = list(tmp_path.rglob("*.jsonl"))
    games = [p for p in logs if p.name != "req.jsonl"]
    assert len(games) == 1
    records = [json.loads(line) for line in games[0].read_text().splitlines()]
    assert records[-2]["phase"] == "confessed" and records[-2]["broken"] == [1, 2, 3]


async def test_losing_game_and_restart(tmp_path):
    c = Client(make_app(tmp_path))
    await c.say("开始审讯")
    await c.say("1号卡反驳证词1")
    await c.say("1号卡反驳证词2")
    lost = await c.say("1号卡反驳证词3")
    assert "律师到了" in lost and "真相是" in lost
    again = await c.say("重新开始")
    assert again.startswith("😌") and "九点到十点" in again
    assert "律师还有二次" in await c.say("1号卡反驳证词1")


async def test_repeat_replays_last_reply(tmp_path):
    c = Client(make_app(tmp_path))
    await c.say("开始")
    card = await c.say("念一下3号卡")
    assert await c.say("再说一遍") == card


async def test_sessions_are_separated_by_device_header(tmp_path):
    app = make_app(tmp_path)
    a = Client(app, headers={"X-Linx-Device-Id": "aa:aa"})
    b = Client(app, headers={"X-Linx-Device-Id": "bb:bb"})
    await a.say("开始")
    await b.say("开始")
    assert "证词一被戳破" in await a.say("2号卡反驳证词1")
    assert "律师还有二次" in await b.say("1号卡反驳证词1")  # b 那局不受 a 影响


async def test_api_key_is_required_when_configured(tmp_path):
    app = make_app(tmp_path, api_key="s3cret")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    body = {"model": "pozhan", "messages": [{"role": "user", "content": "你好"}]}
    assert (await http.post("/v1/chat/completions", json=body)).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await http.post("/v1/chat/completions", json=body, headers=bad)).status_code == 401
    ok = await http.post("/v1/chat/completions", json=body, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert (await http.get("/v1/models")).status_code == 401


async def test_request_log_drops_authorization(tmp_path):
    c = Client(make_app(tmp_path), headers={"Authorization": "Bearer x", "X-Linx-Device-Id": "d1"})
    await c.say("你好")
    entry = json.loads((tmp_path / "req.jsonl").read_text().splitlines()[0])
    assert "authorization" not in {k.lower() for k in entry["headers"]}
    assert entry["headers"]["x-linx-device-id"] == "d1"


@pytest.mark.parametrize(
    ("headers", "body", "key"),
    [
        ({"X-Linx-Device-Id": "d"}, {}, "x-linx-device-id:d"),
        ({"X-Linx-Session-Id": "s"}, {"user": "u"}, "x-linx-session-id:s"),
        ({}, {"user": "u"}, "user:u"),
        ({}, {}, "default"),
    ],
)
def test_session_key_resolution(headers, body, key):
    assert HeaderResolver().resolve(headers, body) == key


async def test_platform_tools_in_request_are_ignored(tmp_path):
    # 「统一意图识别」开启时，平台会在主对话请求里附带 tools；游戏照常处理，不返回工具调用
    app = make_app(tmp_path)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    body = {
        "model": "pozhan",
        "messages": [{"role": "system", "content": "你是小智"}, {"role": "user", "content": "开始审讯"}],
        "tools": [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
    }
    r = await http.post("/v1/chat/completions", json=body)
    message = r.json()["choices"][0]["message"]
    assert "tool_calls" not in message and "九点到十点" in message["content"]


async def test_oversized_body_is_rejected(tmp_path):
    app = make_app(tmp_path)
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    big = {"model": "pozhan", "messages": [{"role": "user", "content": "啊" * 600_000}]}
    assert (await http.post("/v1/chat/completions", json=big)).status_code == 413
    assert (await http.post("/v1/chat/completions", content=b"[1,2]")).status_code == 400


async def test_overlong_utterance_is_truncated(tmp_path):
    c = Client(make_app(tmp_path))
    await c.say("开始")
    await c.say("你" * 5000)
    records = [
        json.loads(x)
        for p in tmp_path.rglob("*.jsonl")
        if p.name != "req.jsonl"
        for x in p.read_text().splitlines()
    ]
    assert len(records[-1]["text"]) == 200
