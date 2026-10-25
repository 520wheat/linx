"""屏幕快照：陪玩屏能看到的全部数据（#36 决策 6）。

这里是结局前防剧透的唯一闸门：哪条证词是谎言、真相、失言目标、矛盾表，结局前都不进快照。
前端拿不到，也就不可能泄露。
"""

from typing import Any

from pozhan.case.model import Case
from pozhan.engine.state import Phase
from pozhan.session.store import Session


def _first_clause(text: str) -> str:
    """让步原文较长（「承认……，但坚称……」），屏幕上只放第一个分句。"""
    for sep in "，,。；;":
        text = text.split(sep, 1)[0]
    return text


def _card_title(case: Case, card_id: int | None) -> str:
    card = case.card(card_id) if card_id is not None else None
    return card.title if card else ""


def build_snapshot(case: Case, session: Session | None, now: float) -> dict[str, Any]:
    state = session.state if session else None
    snap: dict[str, Any] = {
        "serverNow": now,
        "case": {
            "id": case.id,
            "title": case.title,
            "briefing": case.briefing,
            "suspect": {"name": case.suspect.name},
        },
        "rulesText": {"strikes": case.limits.strikes, "minutes": case.limits.minutes},
    }
    if state is None:
        snap["scene"] = "briefing"
        return snap

    broken_by = {x.claim: x for x in case.contradictions if x.claim in state.broken}
    used_cards = {x.card for x in broken_by.values()}
    stage = case.stages[min(state.stage, len(case.stages) - 1)]

    snap.update(
        {
            "scene": "ended" if state.over else "interrogating",
            "claims": [
                {
                    "id": c.id,
                    "text": c.text,
                    "status": "broken" if c.id in broken_by else "holding",
                    **(
                        {
                            "brokenBy": {
                                "card": broken_by[c.id].card,
                                "cardTitle": _card_title(case, broken_by[c.id].card),
                                "concession": _first_clause(broken_by[c.id].concession),
                            }
                        }
                        if c.id in broken_by
                        else {}
                    ),
                }
                for c in case.claims
            ],
            "cards": [{"id": c.id, "title": c.title, "used": c.id in used_cards} for c in case.cards],
            "stages": [s.name for s in case.stages],
            "stage": {"index": state.stage, "name": stage.name, "tone": stage.tone},
            "lawyer": {
                "strikes": state.strikes,
                "limit": case.limits.strikes,
                "startedAt": state.started_at,
                "limitSeconds": case.limits.minutes * 60,
            },
            "line": {"speaker": session.line["speaker"], "text": session.line["text"]}
            if session.line
            else None,
            "event": session.event,
        }
    )

    if state.over:
        ended = session.ended_at or now
        snap["result"] = {
            "won": state.phase is Phase.CONFESSED,
            "phase": state.phase.value,
            "broken": len(state.broken),
            "claimCount": len(case.claims),
            "strikes": state.strikes,
            "elapsedSeconds": max(0, int(ended - state.started_at)),
            "timeline": [
                {"time": t.time, "text": t.text, "card": t.card, "cardTitle": _card_title(case, t.card)}
                for t in case.timeline
            ],
            "reveal": case.reveal,
        }
    return snap
