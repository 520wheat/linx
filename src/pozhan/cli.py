import argparse

import uvicorn

from pozhan.case.demo import DEMO_CASE
from pozhan.director.director import Director
from pozhan.game import Game
from pozhan.intent.interpreter import Interpreter, RuleMatcher
from pozhan.server.app import create_app
from pozhan.session.store import HeaderResolver, MemoryStore


def build_app():
    game = Game(
        case=DEMO_CASE,
        interpreter=Interpreter(RuleMatcher(), classifier=None),
        director=Director(llm=None, model=""),
        store=MemoryStore(),
    )
    return create_app(game, HeaderResolver())


def main() -> None:
    parser = argparse.ArgumentParser(prog="pozhan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="启动 OpenAI 兼容的游戏服务")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.cmd == "serve":
        uvicorn.run(build_app(), host=args.host, port=args.port)
