"""一轮对话的编排：意图 → 规则 → 台词。server 只负责协议，业务流程都在这里。"""

import asyncio
import contextlib
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable

from pozhan.case.model import Case
from pozhan.director import narrator
from pozhan.director.director import NEUTRAL, Director, Line
from pozhan.engine.events import Ask, Command, CommandKind, Event
from pozhan.engine.outcomes import Briefing, Broke, Confession, Lawyer, Outcome, Quit, Repeat, Wrong
from pozhan.engine.rules import apply, new_game
from pozhan.engine.state import Interrogation
from pozhan.gamelog import GameLog
from pozhan.intent.interpreter import Clarify, Interpreter
from pozhan.screen.hub import ScreenHub
from pozhan.screen.snapshot import build_snapshot
from pozhan.session.store import Session, SessionStore

_DONE = object()
_PUNCT_ONLY = re.compile(r"[\s\W_]+")


class _Speculation:
    """规则没命中时，先假设玩家是在提问，提前开始生成嫌疑人的回答（#22）。

    意图分类和这份回答并行进行：分类结果确实是提问就直接用，否则丢弃。
    大多数话都是提问，这样能省掉一次分类的等待。
    """

    def __init__(
        self, director: Director, case: Case, state: Interrogation, outcome: Outcome, session: Session
    ):
        self.state, self.outcome = state, outcome
        self.queue: asyncio.Queue = asyncio.Queue()
        self.task = asyncio.create_task(self._produce(director, case, session))

    async def _produce(self, director: Director, case: Case, session: Session) -> None:
        try:
            async for line in director.speak(case, self.state, self.outcome, session.history):
                await self.queue.put(line)
        finally:
            await self.queue.put(_DONE)

    async def lines(self) -> AsyncIterator[Line]:
        while (line := await self.queue.get()) is not _DONE:
            yield line

    async def cancel(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


class Game:
    def __init__(
        self,
        case: Case,
        interpreter: Interpreter,
        director: Director,
        store: SessionStore,
        log: GameLog | None = None,
        clock: Callable[[], float] = time.time,
        screen: ScreenHub | None = None,
    ) -> None:
        self.case = case
        self.interpreter = interpreter
        self.director = director
        self.store = store
        self.log = log or GameLog(None)
        self.clock = clock
        self.screen = screen

    def _publish(self, session: Session) -> None:
        if self.screen is not None:
            self.screen.publish(session.key, build_snapshot(self.case, session, self.clock()))

    def _mark(self, session: Session, outcome: Outcome | Clarify, prev_stage: int, now: float) -> None:
        """把陪玩屏关心的关键事件记到会话上（#38）。字段只放公开信息。"""
        state = session.state
        event: dict | None = None
        match outcome:
            case Briefing():
                session.line, session.ended_at = None, None
                event = {"kind": "briefing"}
            case Broke(contradiction=x) | Confession(contradiction=x):
                claim, card = self.case.claim(x.claim), self.case.card(x.card)
                event = {
                    "kind": "confession" if isinstance(outcome, Confession) else "broke",
                    "claim": x.claim,
                    "claimText": claim.text if claim else "",
                    "card": x.card,
                    "cardTitle": card.title if card else "",
                    "cardText": card.text if card else "",
                    "fromStage": self.case.stages[prev_stage].name,
                    "toStage": self.case.stages[state.stage].name,
                }
            case Wrong(card=card, claim=claim, strikes_left=left):
                event = {"kind": "wrong", "card": card, "claim": claim, "strikesLeft": left}
            case Lawyer(reason=reason):
                event = {"kind": "lawyer", "reason": reason}
            case Quit():
                event = {"kind": "quit"}
        if event is not None:
            session.event_seq += 1
            session.event = {"id": session.event_seq, **event}
        if state.over and session.ended_at is None:
            session.ended_at = now

    async def turn(self, key: str, text: str, *, voice_emotion: str | None = None) -> AsyncIterator[str]:
        """处理玩家的一句话，按增量产出要说的文本。第一段永远是本轮情绪 emoji。"""
        session = self.store.get_or_create(key)
        async with session.lock:  # 同一局的请求串行处理
            pending: list[_Speculation] = []
            try:
                async for part in self._play(session, key, text, pending, voice_emotion):
                    yield part
            finally:
                # 玩家打断时平台会断开流，这里把还在跑的投机生成一并取消，不留后台任务（#24）
                for spec in pending:
                    spec.task.cancel()

    async def _play(
        self,
        session: Session,
        key: str,
        text: str,
        pending: list["_Speculation"],
        voice_emotion: str | None = None,
    ) -> AsyncIterator[str]:
        t0 = time.monotonic()
        now = self.clock()
        prev_stage = session.state.stage if session.state else 0
        spec: _Speculation | None = None
        event: Event | Clarify

        if session.state is not None and not _PUNCT_ONLY.sub("", text):
            # 识别结果为空（设备没听清）：不推进状态，不调用大模型（#24）
            yield NEUTRAL + narrator.not_heard()
            return

        if session.state is None:
            session.state = new_game(self.case, now)
            event = Command(CommandKind.START)
        elif (matched := self.interpreter.match(text, self.case)) is not None:
            event = matched
        else:
            if not session.state.over:
                guess_state, guess = apply(self.case, session.state, Ask(text), now)
                spec = _Speculation(self.director, self.case, guess_state, guess, session)
                pending.append(spec)
            event = await self.interpreter.classify(text, self.case)
            if spec is not None and event != Ask(text):
                await spec.cancel()
                spec = None
        t_intent = time.monotonic() - t0

        if spec is not None:
            session.state, outcome = spec.state, spec.outcome
            lines = spec.lines()
        else:
            if isinstance(event, Clarify):
                outcome = event
            else:
                session.state, outcome = apply(self.case, session.state, event, now)
            lines = self.director.speak(self.case, session.state, outcome, session.history)

        if isinstance(outcome, Briefing) and (not session.game_id or event == Command(CommandKind.RESTART)):
            session.game_id = uuid.uuid4().hex[:8]
            session.history.clear()

        if isinstance(outcome, Repeat) and session.last_reply:
            self.store.put(session)
            yield session.last_reply
            return

        # 规则结果一出来就推给陪玩屏，不等台词生成：「戳破瞬间」要在 1 秒内出现（#36 验收标准 2）
        self._mark(session, outcome, prev_stage, now)
        self._publish(session)

        emoji = self.director.emoji(self.case, session.state, outcome)
        yield emoji
        parts: list[str] = []
        t_first = None
        async for line in lines:
            t_first = t_first or time.monotonic() - t0
            parts.append(line.text)
            same_turn = session.line is not None and session.line.get("turn") == t0
            if same_turn and session.line["speaker"] == line.speaker:
                session.line = {**session.line, "text": session.line["text"] + line.text}
                self._publish(session)
            elif not (same_turn and session.line["speaker"] == "suspect"):
                # 嫌疑人开口之后，同一轮里的旁白（「他还在坚持……」）不再覆盖字幕
                session.line = {"speaker": line.speaker, "text": line.text, "turn": t0}
                self._publish(session)
            yield line.text

        spoken = "".join(parts)
        session.last_reply = emoji + spoken
        session.remember(text, spoken)
        self.store.put(session)
        self.log.write(
            key,
            session.game_id,
            text=text,
            voice_emotion=voice_emotion,
            event=event,
            outcome=outcome,
            reply=spoken,
            stage=session.state.stage,
            strikes=session.state.strikes,
            broken=session.state.broken,
            phase=session.state.phase,
            speculated=spec is not None,
            intent_s=round(t_intent, 3),
            first_line_s=round(t_first or 0, 3),
            total_s=round(time.monotonic() - t0, 3),
        )
