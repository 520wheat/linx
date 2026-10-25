"""陪玩屏后端测试（#38）：快照内容、防剧透、推送时机、鉴权与 SSE。"""

import asyncio
import json

import httpx
import pytest
import uvicorn

from pozhan.case import load_case
from pozhan.director import Director
from pozhan.game import Game
from pozhan.intent import Interpreter, RuleMatcher
from pozhan.screen import ScreenHub
from pozhan.server import create_app
from pozhan.session import HeaderResolver, MemoryStore
from tests.conftest import GOLDEN_WATCH


class RecordingHub(ScreenHub):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[dict] = []

    def publish(self, key, snapshot):
        self.published.append(json.loads(json.dumps(snapshot, ensure_ascii=False)))
        super().publish(key, snapshot)


def make(token: str = ""):
    case = load_case(GOLDEN_WATCH)
    hub = RecordingHub()
    game = Game(
        case=case,
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
        screen=hub,
    )
    app = create_app(game, HeaderResolver(), screen=hub, screen_token=token)
    return case, hub, app


async def say(http, text, device="dev-1"):
    body = {"model": "pozhan", "messages": [{"role": "user", "content": text}]}
    r = await http.post("/v1/chat/completions", json=body, headers={"X-Linx-Device-Id": device})
    return r.json()["choices"][0]["message"]["content"]


@pytest.fixture
def client_for():
    def _make(app):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")

    return _make


async def test_snapshots_follow_the_game(client_for):
    case, hub, app = make()
    http = client_for(app)
    await say(http, "开始审讯")
    assert hub.published[0]["scene"] == "interrogating" and hub.published[0]["event"]["kind"] == "briefing"

    await say(http, "用二号卡反驳证词一")
    snap = hub.published[-1]
    assert snap["claims"][0]["status"] == "broken"
    assert snap["claims"][0]["brokenBy"] == {
        "card": 2,
        "cardTitle": "电梯监控截图",
        "concession": "承认九点半上过十八楼",
    }
    assert [c["used"] for c in snap["cards"]] == [False, True, False, False]
    assert snap["stage"]["name"] == "狡辩"
    assert snap["event"]["kind"] == "broke" and snap["event"]["fromStage"] == "镇定"
    assert snap["line"]["speaker"] in ("narrator", "suspect")

    await say(http, "用一号卡反驳证词二")
    assert hub.published[-1]["event"] == {"id": 3, "kind": "wrong", "card": 1, "claim": 2, "strikesLeft": 2}
    assert hub.published[-1]["lawyer"]["strikes"] == 1


async def test_broke_event_is_published_before_any_line(client_for):
    _, hub, app = make()
    http = client_for(app)
    await say(http, "开始审讯")
    before = len(hub.published)
    await say(http, "用二号卡反驳证词一")
    first = hub.published[before]
    assert first["event"]["kind"] == "broke"
    assert first["line"] is None or "被戳破" not in first["line"]["text"]  # 台词还没开始，事件已经推出去了


async def test_no_spoilers_before_the_end(client_for):
    case, hub, app = make()
    http = client_for(app)
    for text in ["开始审讯", "你在哪", "用二号卡反驳证词一", "用一号卡反驳证词二", "用三号卡反驳证词二"]:
        await say(http, text)
    secrets = [*case.suspect.truth, case.reveal, *(x.slip for x in case.contradictions)]
    secrets += [t.text for t in case.timeline]
    for snap in hub.published:
        blob = json.dumps(snap, ensure_ascii=False)
        assert '"lie"' not in blob and "result" not in snap
        for secret in secrets:
            assert secret not in blob

    await say(http, "用四号卡反驳证词三")
    final = hub.published[-1]
    assert final["scene"] == "ended" and final["result"]["won"] is True
    assert final["result"]["broken"] == 3 and final["result"]["strikes"] == 1
    assert [t["cardTitle"] for t in final["result"]["timeline"]][1] == "电梯监控截图"


async def test_card_texts_are_on_screen_from_the_start(client_for):
    # 网页开玩的玩家没有实体卡，开局前就要能在屏幕上看到卡面（#43）
    case, hub, app = make()
    http = client_for(app)
    before = (await http.get("/screen/state")).json()
    assert [c["text"] for c in before["cards"]] == [c.text for c in case.cards]
    assert not any(c["used"] for c in before["cards"])
    await say(http, "开始审讯")
    await say(http, "用二号卡反驳证词一")
    used = {c["id"]: c["used"] for c in hub.published[-1]["cards"]}
    assert used == {1: False, 2: True, 3: False, 4: False}


async def test_losing_result(client_for):
    _, hub, app = make()
    http = client_for(app)
    await say(http, "开始")
    for claim in (1, 2, 3):
        await say(http, f"用一号卡反驳证词{claim}")
    result = hub.published[-1]["result"]
    assert result["won"] is False and result["phase"] == "lawyer" and result["strikes"] == 3


async def test_state_endpoint_token_and_device(client_for):
    _, hub, app = make(token="t0k")
    http = client_for(app)
    assert (await http.get("/screen/state")).status_code == 401
    assert (await http.get("/screen/state?token=bad")).status_code == 401
    idle = (await http.get("/screen/state?token=t0k")).json()
    assert idle["scene"] == "briefing" and idle["case"]["title"] == "年会夜的金表"
    assert idle["library"][0]["id"] == idle["case"]["id"]

    await say(http, "开始", device="aa:bb")
    await say(http, "开始", device="cc:dd")
    await say(http, "用二号卡反驳证词一", device="aa:bb")
    a = (await http.get("/screen/state?token=t0k&device=aa:bb")).json()
    c = (await http.get("/screen/state?token=t0k&device=cc:dd")).json()
    assert a["claims"][0]["status"] == "broken" and c["claims"][0]["status"] == "holding"
    latest = (await http.get("/screen/state?token=t0k")).json()
    assert latest["claims"][0]["status"] == "broken"  # 不指定设备时跟随最近活跃的一局


async def test_screen_page_is_served(client_for):
    _, _, app = make(token="x")
    r = await client_for(app).get("/screen")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


async def test_events_stream_initial_snapshot_and_updates():
    _, hub, app = make(token="t0k")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(base_url=base, timeout=5) as http:
            async with http.stream("GET", "/screen/events?token=t0k") as r:
                assert r.status_code == 200
                lines = r.aiter_lines()
                first = await anext(line async for line in lines if line.startswith("data: "))
                assert json.loads(first[6:])["scene"] == "briefing"
                await say(http, "开始审讯")
                update = await anext(line async for line in lines if line.startswith("data: "))
                assert json.loads(update[6:])["scene"] == "interrogating"
            r = await http.get("/screen/events?token=nope")
            assert r.status_code == 401
    finally:
        server.should_exit = True
        await task


async def test_subtitle_keeps_the_suspect_line_over_trailing_narration(client_for):
    _, hub, app = make()
    http = client_for(app)
    await say(http, "开始审讯")
    await say(http, "用二号卡反驳证词一")
    assert hub.published[-1]["line"]["speaker"] == "suspect"


async def test_subscription_survives_idle_timeouts():
    hub = ScreenHub()
    q = hub.subscribe("*")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.05)  # 空闲超时（发 keepalive 的时机）
    hub.publish("k", {"scene": "briefing"})
    assert (await asyncio.wait_for(q.get(), timeout=1))["scene"] == "briefing"  # 超时之后仍能收到推送
    hub.unsubscribe("*", q)
    hub.publish("k", {"scene": "ended"})
    assert q.empty()


def test_device_subscription_before_first_publish():
    hub = ScreenHub()
    q = hub.subscribe("aa:bb")  # 屏幕先打开，设备还没说话
    hub.publish("x-linx-device-id:cc:dd", {"n": 1})
    hub.publish("x-linx-device-id:aa:bb", {"n": 2})
    assert q.get_nowait() == {"n": 2} and q.empty()


async def test_screen_follows_the_case_switch(client_for):
    from dataclasses import replace

    case = load_case(GOLDEN_WATCH)
    other = replace(case, id="other", title="另一个案子")
    hub = RecordingHub()
    game = Game(
        case=case,
        cases=(case, other),
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
        screen=hub,
    )
    http = client_for(create_app(game, HeaderResolver(), screen=hub))
    await say(http, "开始审讯")
    assert hub.published[-1]["case"]["title"] == case.title
    await say(http, "下一个案子")
    assert hub.published[-1]["case"]["title"] == "另一个案子"
    assert hub.published[-1]["event"]["kind"] == "briefing"
    await say(http, "切换到案子 golden-watch")
    last = hub.published[-1]
    assert last["case"]["id"] == "golden-watch" and last["event"]["kind"] == "briefing"
    assert [c["id"] for c in last["library"]] == ["golden-watch", "other"]


async def test_root_redirects_to_web_play_keeping_the_token(client_for):
    _, _, app = make()
    http = client_for(app)
    r = await http.get("/?token=abc")
    assert r.status_code == 307 and r.headers["location"] == "/screen?play=1&token=abc"
    r = await http.get("/")
    assert r.headers["location"] == "/screen?play=1"


async def test_art_is_served_without_a_token(client_for, tmp_path):
    # 美术资源不含对局数据（#61）：不需要令牌；不存在的图返回 404，页面会退回首字圆章
    _, _, app = make(token="secret")
    http = client_for(app)
    missing = await http.get("/screen/img/no-such-case/suspect.jpg")
    assert missing.status_code == 404
    from pozhan.screen import PAGE

    shipped = sorted((PAGE.parent / "img").glob("*/suspect.jpg"))
    if shipped:
        r = await http.get(f"/screen/img/{shipped[0].parent.name}/suspect.jpg")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


async def test_select_endpoint_switches_case(client_for):
    from dataclasses import replace

    case = load_case(GOLDEN_WATCH)
    other = replace(case, id="other", title="另一个案子")
    hub = RecordingHub()
    game = Game(
        case=case,
        cases=(case, other),
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
        screen=hub,
    )
    http = client_for(create_app(game, HeaderResolver(), screen=hub, screen_token="t0k"))
    assert (await http.post("/screen/select", json={"id": "other"})).status_code == 401
    idle = (await http.get("/screen/state?token=t0k")).json()
    assert idle["case"]["id"] == "golden-watch"
    r = await http.post("/screen/select?token=t0k&device=dev-1", json={"id": "other"})
    assert r.status_code == 200
    body = r.json()
    assert body["case"]["id"] == "other" and body["case"]["title"] == "另一个案子"
    assert body["scene"] == "briefing"
    assert [c["id"] for c in body["library"]] == ["golden-watch", "other"]
    assert (await http.get("/screen/state?token=t0k&device=dev-1")).json()["scene"] == "briefing"
    await say(http, "开始审讯", device="dev-1")
    started = (await http.get("/screen/state?token=t0k&device=dev-1")).json()
    assert started["case"]["id"] == "other" and started["scene"] == "interrogating"
    missing = await http.post("/screen/select?token=t0k", json={"id": "nope"})
    assert missing.status_code == 404


async def test_screen_page_embeds_the_case_list(client_for):
    _, _, app = make()
    r = await client_for(app).get("/screen")
    assert r.status_code == 200
    html = r.text
    assert "年会夜的金表" in html
    assert "/*BOOT_LIBRARY*/null" not in html
