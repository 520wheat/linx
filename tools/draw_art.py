# ruff: noqa: E501  提示词是英文长句，按句子折行比按 110 列折行更好读
"""陪玩屏美术（#61、#63）：用七牛 MAAS 的 openai/gpt-image-2 生成嫌疑人立绘、案件封面和线索卡插图。

同一套风格前缀保证几张图放在一起是一个系列；生成的原图放 art/raw/（不进仓库），
压缩后的成品放 src/pozhan/screen/static/img/<案件 id>/。
需要环境变量 LLM_BASE_URL、LLM_API_KEY。
用法：uv run python tools/draw_art.py [案件 id ...]
"""

import asyncio
import base64
import os
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "art" / "raw"
OUT = ROOT / "src" / "pozhan" / "screen" / "static" / "img"
MODEL = os.environ.get("IMAGE_MODEL", "openai/gpt-image-2")

STYLE = (
    "Editorial illustration for a Chinese detective voice game. Clean flat-vector style with a subtle paper grain, "
    "soft cool grey palette (light grey #F0F2F4, slate #2A3644) with a single warm coral accent (#D9825B). "
    "Calm, premium, slightly playful, not cartoonish. Absolutely no text, letters, numbers, logos or watermarks."
)
PORTRAIT = "Head-and-shoulders portrait, centered, facing slightly to the left, plain light grey background. "
COVER = "Wide establishing shot of the scene, no people, gentle depth, room for a title on the left third. "
CARD = "An evidence photo for a case board: the object centered on a plain light grey background, soft shadow, no frame. "

# 线索卡插图（#63）：只画卡上说的证物，人物和读得出的文字都不画清楚，免得和卡面文字矛盾
CARDS = {
    "missing-pudding": {
        1: "A tablet showing an empty meeting-room booking calendar grid where every afternoon slot is blank, next to a door keycard reader.",
        2: "A ceiling security-camera still of an office pantry: a young man in a dark hoodie, seen from behind, opening a fridge and taking out a small box.",
        3: "An open office desk drawer overflowing with chocolate bars, small cakes and jelly cups.",
        4: "A small pantry trash bin with a little spoon smeared with whipped cream lying on top.",
    },
    "golden-watch": {
        1: "A karaoke song-request screen with an empty queue, a microphone resting beside it, dim neon karaoke room light.",
        2: "A grainy elevator security-camera still: a man in a white shirt and loose dark tie standing alone, an up-arrow floor indicator glowing.",
        3: "A yellow sticky note stuck on the side of an office printer, covered in illegible handwritten scribbles.",
        4: "A forensic fingerprint card with a dusted fingerprint next to an open watch box holding a gold wristwatch with a metal bracelet (not a pocket watch), and a magnifying glass.",
        5: "A company party display table under spotlights with boxed prize models and an empty velvet watch stand.",
        6: "A storage-room door with an unlit keycard reader, and a stack of snack gift bags placed in a karaoke room.",
    },
    "livestream-bracelet": {
        1: "A smartphone gallery screen showing a video thumbnail of a late-night snack mukbang with a play button.",
        2: "A smart door lock on a guesthouse door with a spare keycard, and a small inset security-camera view of a hand rummaging in a front-desk drawer.",
        3: "A laptop showing a livestream analytics dashboard with flat zero lines on every engagement chart and a muted microphone icon.",
        4: "A phone showing an empty food-delivery order list beside a guesthouse front-desk logbook.",
        5: "A phone showing a social-media photo of a jade bracelet lying on a wooden dressing table.",
        6: "A phone showing a livestream replay with only a few sparse chat bubbles in an empty comment area.",
    },
    "library-badge": {
        1: "A security-camera still of a young man with round glasses and a red lanyard swiping a card at a rare-book room door.",
        2: "A traditional Chinese cloth book case dusted with fingerprint powder, a forensic brush beside it.",
        3: "A sign-out clipboard with a signature line, an access card on a red lanyard lying on top.",
        4: "An antique handwritten manuscript page under a violet forensic lamp revealing a faint thumbprint on its lining paper.",
        5: "Online shopping parcels opened on a dorm desk: rolls of aged xuan paper, ink sticks and a bag of tea leaves.",
        6: "A library book on calligraphy authentication with a borrowing slip tucked between its pages.",
    },
}

ART = {
    "golden-watch": {
        "suspect": "A 38-year-old Chinese office administration manager, neat short hair, white shirt with a loosened "
        "dark tie, a polite but nervous smile, a bead of sweat on the temple.",
        "cover": "An executive office on the 18th floor at night after a company party: a small wall safe slightly open "
        "with an empty watch box inside, city lights through the window, a few party streamers on the floor.",
    },
    "livestream-bracelet": {
        "suspect": "A 25-year-old Chinese female food livestreamer, sweet round face, a hair clip, oversized hoodie, "
        "holding a smartphone, a slightly guilty sideways glance.",
        "cover": "A cozy guesthouse room at night: a phone on a tripod with a ring light streaming a bowl of late-night "
        "snacks, and in the background an empty jade-green jewelry dish on a dressing table.",
    },
    "library-badge": {
        "suspect": "A 24-year-old Chinese male library intern, round glasses, beige cardigan, a lanyard with an access "
        "card, shy and timid expression.",
        "cover": "A quiet rare-book room in a city library: a glass display case with an antique handwritten manuscript "
        "page, an access-card reader beside the door, soft afternoon light.",
    },
    "missing-pudding": {
        "suspect": "A 26-year-old Chinese male graphic designer, messy hair, comfy hoodie, a sheepish grin with a tiny "
        "smear of cream at the corner of his mouth.",
        "cover": "A bright office pantry in the afternoon: a fridge with a small sticky note, an empty pudding cup and "
        "a little spoon on the counter, a new coffee machine.",
    },
}

SIZES = {"suspect": "1024x1024", "cover": "1536x1024", "card": "1024x1024"}
# 成品：立绘 512 方图，封面 1200 宽，线索卡 400 方图；JPEG 80 足够屏幕和打印使用
FINAL = {"suspect": 512, "cover": 1200, "card": 400}


def prompt_for(case_id: str, kind: str) -> str:
    if kind.startswith("card-"):
        return STYLE + " " + CARD + CARDS[case_id][int(kind.removeprefix("card-"))]
    return STYLE + " " + (PORTRAIT if kind == "suspect" else COVER) + ART[case_id][kind]


async def draw(client: httpx.AsyncClient, case_id: str, kind: str, sem: asyncio.Semaphore) -> None:
    raw = RAW / case_id / f"{kind}.png"
    size = kind.split("-")[0]  # card-3 → card
    if not raw.exists():
        prompt = prompt_for(case_id, kind)
        async with sem:
            r = await client.post(
                f"{os.environ['LLM_BASE_URL'].rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
                json={"model": MODEL, "prompt": prompt, "size": SIZES[size], "n": 1},
            )
        r.raise_for_status()
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
    out = OUT / case_id / f"{kind}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "sips",
            "-Z",
            str(FINAL[size]),
            "-s",
            "format",
            "jpeg",
            "-s",
            "formatOptions",
            "80",
            str(raw),
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    print(f"{case_id}/{kind}: {out.stat().st_size // 1024} KB")


async def main(case_ids: list[str]) -> None:
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=600) as client:
        jobs = [
            draw(client, c, k, sem)
            for c in case_ids
            for k in ["suspect", "cover", *(f"card-{i}" for i in CARDS.get(c, {}))]
        ]
        for result in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(result, Exception):
                print("失败：", repr(result))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or list(ART)))
