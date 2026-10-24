import argparse
import logging
import os
import sys
from pathlib import Path

import uvicorn

from pozhan.cards import render as render_cards
from pozhan.case import load_case, validate
from pozhan.config import Settings
from pozhan.director.director import Director
from pozhan.game import Game
from pozhan.gamelog import GameLog
from pozhan.intent import Interpreter, LLMClassifier, RuleMatcher
from pozhan.llm import OpenAICompatLLM
from pozhan.server.app import create_app
from pozhan.session.store import HeaderResolver, MemoryStore

log = logging.getLogger("pozhan")


def build_app(settings: Settings | None = None):
    settings = settings or Settings.from_env()
    case = load_case(settings.case_path)
    problems = validate(case)
    if problems:
        raise SystemExit("案件校验未通过：" + "；".join(p.message for p in problems))

    intent_llm = suspect_llm = None
    if settings.llm_enabled:
        intent_llm = OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key, temperature=0.0)
        suspect_llm = OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key, temperature=0.8)
    else:
        log.warning("未配置 LLM_BASE_URL / LLM_API_KEY：只走规则匹配，嫌疑人只会说兜底台词")
    if not settings.api_key:
        log.warning("未配置 POZHAN_API_KEY：接口不校验密钥，只适合本地开发")

    game = Game(
        case=case,
        interpreter=Interpreter(
            RuleMatcher(),
            LLMClassifier(intent_llm, settings.intent_model) if intent_llm else None,
        ),
        director=Director(suspect_llm, settings.suspect_model),
        store=MemoryStore(),
        log=GameLog(Path(settings.log_dir) / "games" if settings.log_dir else None),
    )
    request_log = Path(settings.log_dir) / "requests.jsonl" if settings.log_requests else None
    return create_app(game, HeaderResolver(), api_key=settings.api_key, request_log=request_log)


def check(path: str) -> int:
    problems = validate(load_case(path))
    for p in problems:
        print(f"[{p.rule}] {p.message}")
    print("校验通过" if not problems else f"共 {len(problems)} 个问题")
    return 1 if problems else 0


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(prog="pozhan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="启动 OpenAI 兼容的游戏服务（配置见环境变量，README 有说明）")
    serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    chk = sub.add_parser("check", help="校验案件文件")
    chk.add_argument("path")
    cards = sub.add_parser("cards", help="生成可打印的线索卡（HTML，浏览器打开后打印）")
    cards.add_argument("path", help="案件文件")
    cards.add_argument("-o", "--out", default="cards.html")
    args = parser.parse_args()

    if args.cmd == "serve":
        uvicorn.run(build_app(), host=args.host, port=args.port)
    elif args.cmd == "check":
        sys.exit(check(args.path))
    elif args.cmd == "cards":
        Path(args.out).write_text(render_cards(load_case(args.path)), encoding="utf-8")
        print(f"已生成 {args.out}：用浏览器打开后打印（A4，一页四张）")
