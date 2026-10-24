from pathlib import Path
from typing import Any

import yaml

from pozhan.case.model import Card, Case, Claim, Contradiction, Limits, Stage, Suspect


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
            briefing=_require(data, "briefing", "案件").strip(),
            suspect=Suspect(
                name=_require(suspect, "name", "suspect"),
                persona=_require(suspect, "persona", "suspect").strip(),
                truth=tuple(suspect.get("truth") or ()),
            ),
            claims=tuple(
                Claim(
                    id=int(_require(c, "id", "claim")),
                    text=_require(c, "text", "claim"),
                    lie=bool(c.get("lie")),
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
                    concession=_require(x, "concession", "contradiction"),
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
            reveal=_require(data, "reveal", "案件").strip(),
            limits=Limits(strikes=int(limits.get("strikes", 3)), minutes=int(limits.get("minutes", 15))),
        )
    except (TypeError, ValueError) as e:
        if isinstance(e, CaseFormatError):
            raise
        raise CaseFormatError(f"案件字段类型不对：{e}") from e


def load_case(path: str | Path) -> Case:
    with open(path, encoding="utf-8") as f:
        return parse_case(yaml.safe_load(f))
