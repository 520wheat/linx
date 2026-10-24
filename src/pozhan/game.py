"""一轮对话的编排：意图 → 规则 → 台词。server 只负责协议，业务流程都在这里。"""

import time
import uuid
from collections.abc import AsyncIterator, Callable

from pozhan.case.model import Case
from pozhan.director.director import Director
from pozhan.engine.events import Command, CommandKind
from pozhan.engine.outcomes import Briefing, Repeat
from pozhan.engine.rules import apply, new_game
from pozhan.gamelog import GameLog
from pozhan.intent.interpreter import Clarify, Interpreter
from pozhan.session.store import SessionStore


class Game:
    def __init__(
        self,
        case: Case,
        interpreter: Interpreter,
        director: Director,
        store: SessionStore,
        log: GameLog | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.case = case
        self.interpreter = interpreter
        self.director = director
        self.store = store
        self.log = log or GameLog(None)
        self.clock = clock

    async def turn(self, key: str, text: str) -> AsyncIterator[str]:
        """处理玩家的一句话，按增量产出要说的文本。第一段永远是本轮情绪 emoji。"""
        session = self.store.get_or_create(key)
        async with session.lock:  # 同一局的请求串行处理
            t0 = time.monotonic()
            now = self.clock()
            if session.state is None:
                session.state = new_game(self.case, now)
                event = Command(CommandKind.START)
            else:
                event = await self.interpreter.interpret(text, self.case)
            t_intent = time.monotonic() - t0

            if isinstance(event, Clarify):
                outcome = event
            else:
                session.state, outcome = apply(self.case, session.state, event, now)
            if isinstance(outcome, Briefing) and (
                not session.game_id or event == Command(CommandKind.RESTART)
            ):
                session.game_id = uuid.uuid4().hex[:8]
                session.history.clear()

            if isinstance(outcome, Repeat) and session.last_reply:
                self.store.put(session)
                yield session.last_reply
                return

            emoji = self.director.emoji(self.case, session.state, outcome)
            yield emoji
            parts: list[str] = []
            t_first = None
            async for line in self.director.speak(self.case, session.state, outcome, session.history):
                t_first = t_first or time.monotonic() - t0
                parts.append(line.text)
                yield line.text

            spoken = "".join(parts)
            session.last_reply = emoji + spoken
            session.remember(text, spoken)
            self.store.put(session)
            self.log.write(
                key,
                session.game_id,
                text=text,
                event=event,
                outcome=outcome,
                reply=spoken,
                stage=session.state.stage,
                strikes=session.state.strikes,
                broken=session.state.broken,
                phase=session.state.phase,
                intent_s=round(t_intent, 3),
                first_line_s=round(t_first or 0, 3),
                total_s=round(time.monotonic() - t0, 3),
            )
