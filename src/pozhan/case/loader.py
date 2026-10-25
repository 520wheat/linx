import re
from pathlib import Path
from typing import Any

import yaml

from pozhan.case.model import (
    Card,
    Case,
    Claim,
    Contradiction,
    Limits,
    Stage,
    Suspect,
    TimelineStep,
    Unlock,
    WeakEvidence,
)


def _tidy(text: str) -> str:
    """YAML 折行会在中文句子之间留下空格（「……不见了。 监控显示……」），去掉它们。"""
    return re.sub(r"(?<=[\u3000-\u303f\uff00-\uffef\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text.strip())


def _unlock(data: Any) -> Unlock | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise CaseFormatError("claim 的 unlock 应该是对象")
    after = data.get("after")
    return Unlock(
        topic=str(data.get("topic") or ""),
        examples=tuple(str(x) for x in data.get("examples") or ()),
        after=int(after) if after is not None else None,
    )


class CaseFormatError(ValueError):
    """案件文件缺字段或类型不对，message 指明是哪个字段。"""


def _require(data: dict[str, Any], key: str, where: str) -> Any:
    if key not in data or data[key] in (None, ""):
        raise CaseFormatError(f"{where} 缺少字段 {key}")
    return data[key]


def _list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = _require(data, key, "案件")
    if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        raise CaseFormatError(f"案件字段 {key} 应该是对象列表")
    return value


def parse_case(data: dict[str, Any]) -> Case:
    if not isinstance(data, dict):
        raise CaseFormatError("案件文件的顶层应该是一个对象")

    suspect = _require(data, "suspect", "案件")
    limits = data.get("limits") or {}
    try:
        return Case(
            id=str(_require(data, "id", "案件")),
            title=_require(data, "title", "案件"),
            briefing=_tidy(_require(data, "briefing", "案件")),
            suspect=Suspect(
                name=_require(suspect, "name", "suspect"),
                persona=_tidy(_require(suspect, "persona", "suspect")),
                truth=tuple(suspect.get("truth") or ()),
                confession=_tidy(suspect.get("confession") or ""),
            ),
            claims=tuple(
                Claim(
                    id=int(_require(c, "id", "claim")),
                    text=_require(c, "text", "claim"),
                    lie=bool(c.get("lie")),
                    unlock=_unlock(c.get("unlock")),
                )
                for c in _list(data, "claims")
            ),
            cards=tuple(
                Card(
                    id=int(_require(c, "id", "card")),
                    title=_require(c, "title", "card"),
                    text=_require(c, "text", "card"),
                )
                for c in _list(data, "cards")
            ),
            contradictions=tuple(
                Contradiction(
                    card=int(_require(x, "card", "contradiction")),
                    claim=int(_require(x, "claim", "contradiction")),
                    concession=_tidy(_require(x, "concession", "contradiction")),
                    slip=x.get("slip") or "",
                )
                for x in _list(data, "contradictions")
            ),
            stages=tuple(
                Stage(
                    name=_require(s, "name", "stage"),
                    emoji=_require(s, "emoji", "stage"),
                    tone=_require(s, "tone", "stage"),
                    slip_every=int(s.get("slip_every", 6)),
                )
                for s in _list(data, "stages")
            ),
            reveal=_tidy(_require(data, "reveal", "案件")),
            limits=Limits(strikes=int(limits.get("strikes", 3)), minutes=int(limits.get("minutes", 15))),
            timeline=tuple(
                TimelineStep(
                    text=_tidy(_require(t, "text", "timeline")),
                    time=str(t.get("time") or ""),
                    card=int(t["card"]) if t.get("card") is not None else None,
                )
                for t in (data.get("timeline") or [])
            ),
            weak=tuple(
                WeakEvidence(
                    card=int(_require(w, "card", "weak")),
                    claim=int(_require(w, "claim", "weak")),
                    reason=_tidy(_require(w, "reason", "weak")),
                )
                for w in (data.get("weak") or [])
            ),
        )
    except (TypeError, ValueError) as e:
        if isinstance(e, CaseFormatError):
            raise
        raise CaseFormatError(f"案件字段类型不对：{e}") from e


def load_case(path: str | Path) -> Case:
    with open(path, encoding="utf-8") as f:
        return parse_case(yaml.safe_load(f))
