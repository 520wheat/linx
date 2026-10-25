"""整局时延评测：用真实模型、经过完整的 OpenAI 兼容接口打一局，统计每轮「收到请求 → 第一段台词」的时间。

不经过灵矽，衡量的是我们自己这一段的延迟（#22）。服务跑在本机的真实端口上：
httpx 的 ASGITransport 会把流式响应攒齐了才返回，用它测出来的「首段」其实是整轮总时长。
需要环境变量 LLM_BASE_URL、LLM_API_KEY。
用法：uv run python evals/play_latency.py [脚本文件，默认 scripts/win.txt]
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import uvicorn

from pozhan.cli import build_app
from pozhan.config import Settings

ROOT = Path(__file__).resolve().parent.parent


async def main(script: Path) -> None:
    settings = Settings.from_env()
    app = build_app(Settings(**{**settings.__dict__, "log_dir": "", "api_key": ""}))
    lines = [ln.strip() for ln in script.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    firsts = []
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60) as http:
        for text in lines:
            body = {"model": "pozhan", "stream": True, "messages": [{"role": "user", "content": text}]}
            t0 = time.monotonic()
            first, reply = None, ""
            async with http.stream("POST", "/v1/chat/completions", json=body) as r:
                async for line in r.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    delta = json.loads(line[6:])["choices"][0]["delta"].get("content") or ""
                    if delta and len(delta) > 1:  # 跳过单独的情绪 emoji
                        first = first or time.monotonic() - t0
                    reply += delta
            total = time.monotonic() - t0
            firsts.append(first or total)
            print(f"[首段 {first or 0:4.2f}s / 全部 {total:4.2f}s] {text}\n    → {reply[:90]}")
    server.should_exit = True
    await task
    s = sorted(firsts)
    print(f"\n首段时延 p50 {s[len(s) // 2]:.2f}s，最大 {s[-1]:.2f}s（共 {len(s)} 轮）")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "scripts" / "win.txt"))
