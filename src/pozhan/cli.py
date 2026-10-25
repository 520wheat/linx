import argparse
import os
import sys

import uvicorn

from pozhan.case import load_case, validate
from pozhan.director.director import Director
from pozhan.game import Game
from pozhan.intent.interpreter import Interpreter, RuleMatcher
from pozhan.server.app import create_app
from pozhan.session.store import HeaderResolver, MemoryStore

DEFAULT_CASE = "cases/golden-watch.yaml"


def build_app(case_path: str = DEFAULT_CASE):
    game = Game(
        case=load_case(case_path),
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
    )
    return create_app(game, HeaderResolver())


def check(path: str) -> int:
    problems = validate(load_case(path))
    for p in problems:
        print(f"[{p.rule}] {p.message}")
    print("校验通过" if not problems else f"共 {len(problems)} 个问题")
    return 1 if problems else 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="pozhan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="启动 OpenAI 兼容的游戏服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--case", default=os.environ.get("POZHAN_CASE", DEFAULT_CASE))
    chk = sub.add_parser("check", help="校验案件文件")
    chk.add_argument("path")
    args = parser.parse_args()

    if args.cmd == "serve":
        uvicorn.run(build_app(args.case), host=args.host, port=args.port)
    elif args.cmd == "check":
        sys.exit(check(args.path))
