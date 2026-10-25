# ruff: noqa: E501  提示词是英文长句，按句子折行比按 110 列折行更好读
"""陪玩屏美术（#61）：用七牛 MAAS 的 openai/gpt-image-2 生成嫌疑人立绘和案件封面。

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

SIZES = {"suspect": "1024x1024", "cover": "1536x1024"}
# 成品：立绘 512 方图，封面 1200 宽；JPEG 80 足够屏幕使用
FINAL = {"suspect": 512, "cover": 1200}


async def draw(client: httpx.AsyncClient, case_id: str, kind: str, sem: asyncio.Semaphore) -> None:
    raw = RAW / case_id / f"{kind}.png"
    if not raw.exists():
        prompt = STYLE + " " + (PORTRAIT if kind == "suspect" else COVER) + ART[case_id][kind]
        async with sem:
            r = await client.post(
                f"{os.environ['LLM_BASE_URL'].rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
                json={"model": MODEL, "prompt": prompt, "size": SIZES[kind], "n": 1},
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
            str(FINAL[kind]),
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
    sem = asyncio.Semaphore(4)
    async with httpx.AsyncClient(timeout=600) as client:
        jobs = [draw(client, c, k, sem) for c in case_ids for k in ("suspect", "cover")]
        for result in await asyncio.gather(*jobs, return_exceptions=True):
            if isinstance(result, Exception):
                print("失败：", repr(result))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or list(ART)))
