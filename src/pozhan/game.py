"""一轮对话的编排：意图 → 规则 → 台词。server 只负责协议，业务流程都在这里。"""

import time
from collections.abc import AsyncIterator, Callable

from pozhan.case.model import Case
from pozhan.director.director import Director
from pozhan.engine.events import Command, CommandKind
from pozhan.engine.rules import apply, new_game
from pozhan.intent.interpreter import Clarify, Interpreter
from pozhan.llm.client import Message
from pozhan.session.store import Session, SessionStore


class Game:
    def __init__(
        self,
        case: Case,
        interpreter: Interpreter,
        director: Director,
        store: SessionStore,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.case = case
        self.interpreter = interpreter
        self.director = director
        self.store = store
        self.clock = clock

    async def turn(self, key: str, text: str, history: list[Message]) -> AsyncIterator[str]:
        """处理玩家的一句话，按增量产出要说的文本。第一段永远是本轮情绪 emoji。"""
        now = self.clock()
        session = self.store.get(key) or Session(key=key)

        if session.state is None:
            session.state = new_game(self.case, now)
            event = Command(CommandKind.START)
        else:
            event = await self.interpreter.interpret(text, self.case)

        if isinstance(event, Clarify):
            outcome = event
        else:
            session.state, outcome = apply(self.case, session.state, event, now)

        reply = [self.director.emoji(self.case, session.state)]
        yield reply[0]
        async for line in self.director.speak(self.case, session.state, outcome, history):
            reply.append(line.text)
            yield line.text

        session.last_reply = "".join(reply)
        self.store.put(session)
