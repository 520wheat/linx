from pozhan.case.model import Case
from pozhan.engine.events import Ask, Event
from pozhan.engine.outcomes import Answer, Outcome
from pozhan.engine.state import Interrogation


def new_game(case: Case, now: float) -> Interrogation:
    return Interrogation(case_id=case.id, started_at=now)


def apply(case: Case, state: Interrogation, event: Event, now: float) -> tuple[Interrogation, Outcome]:
    """对一个事件推进状态。完整规则见 #7，这里只是桩实现。"""
    question = event.text if isinstance(event, Ask) else ""
    return state, Answer(question=question)
