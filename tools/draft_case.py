"""出案子流水线第一步（#53）：大模型按格式写初稿，校验器和设计检查不通过就带着问题让它改，最多改 3 轮。

初稿只是起点：之后跑 AI 自对弈（evals/selfplay.py），再人工审读，才能合并进 cases/。
需要环境变量 LLM_BASE_URL、LLM_API_KEY；CASE_MODEL 指定写稿模型。
用法：uv run python tools/draft_case.py <案件 id> "<核心诡计和背景，一两句话>"
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import yaml

from pozhan.case import CaseFormatError, parse_case, validate
from pozhan.case.model import Case
from pozhan.llm import OpenAICompatLLM

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("CASE_MODEL", "deepseek/deepseek-v4-pro")
EXAMPLE = ROOT / "cases" / "golden-watch.yaml"
EMOJIS = ("😌", "😠", "😲", "😭")  # 当前音色实测支持的情绪（#29）
MAX_ROUNDS = 3

PROMPT = """你是语音推理游戏《破绽》的案件编剧。
玩家扮演侦探，用语音审问一个嫌疑人，靠追问和出示线索卡戳穿他的谎话。
请按下面范例的 YAML 格式，写一个全新的案件。范例里的注释说明了每个字段的用法。

## 这次的案件
id：{case_id}
核心诡计和背景：{idea}

## 设计要求
- 全部用中文。日常场景里的盗窃、调包、冒用之类的案子，不要暴力、血腥和真实品牌、真实人物。
- 嫌疑人就是真凶。真相（suspect.truth）写成 6～9 条短句，
  覆盖每张线索卡说到的事实，也要说明每条谎话为什么是假的。
- 证词 4～5 条，全部是谎话（lie: true），每条不超过 30 个字，像嫌疑人随口说的话：
  - 开场就说的证词正好 2 条（不写 unlock）；
  - 至少 1 条要靠追问才说出口：写 unlock.topic（四到八个字的话题）和 3 个提问例句；
  - 至少 1 条是被戳破后改口说出的新谎话：写 unlock.after，内容要和那条证词的让步（concession）说法一致。
- 线索卡比谎话多 1 张：每条谎话恰好被一张卡戳破；
  另有 1 张卡哪条都戳不破，但和某条证词沾边，把它登记成 weak（间接证据），并写清楚为什么不够硬。
- 卡的标题是证物名（四到八个字），不要直接复述证词；卡的内容是客观事实，一两句话。
- 每条矛盾都要写 concession（被戳破后承认什么）和 slip（卡关时说漏的一句话，要指向那张卡；
  隐藏证词那条的 slip 要引导侦探去问那个话题）。
- stages 固定 4 档，emoji 依次用 😌 😠 😲 😭，名字依次是 镇定、狡辩、慌乱、崩溃；
  第二、三档写 slip_every（5 和 4）。
- suspect.stolen 列出被盗物的几种叫法（例如 [金表, 表]）；
- briefing 不超过 3 句、110 个字；suspect.confession 写认罪时要说出的内容和动机；
  reveal 写真相总结；timeline 4～6 步，尽量标上时间和对应的卡。
- limits：strikes 3，minutes 15。

## 范例
```yaml
{example}
```

只输出新案件的 YAML，不要任何解释，也不要再输出范例。"""

FIX = """这份初稿有下面这些问题，请修改后输出完整的 YAML（只输出 YAML）：
{problems}"""


def design_problems(case: Case) -> list[str]:
    """校验器管「公平、可解」，这里再管本期的设计要求（#46、#49、#50）。"""
    problems = []
    if len(case.opening_claims) != 2:
        problems.append(f"开场证词应该正好 2 条，现在是 {len(case.opening_claims)} 条")
    if not any(c.unlock and c.unlock.topic for c in case.claims):
        problems.append("至少要有 1 条靠追问才说出口的证词（unlock.topic）")
    if not any(c.unlock and c.unlock.after is not None and not c.unlock.topic for c in case.claims):
        problems.append("至少要有 1 条被戳破后改口说出的证词（只写 unlock.after）")
    if not case.weak:
        problems.append("至少要登记 1 条间接证据（weak）")
    if tuple(s.emoji for s in case.stages) != EMOJIS:
        problems.append(f"stages 的 emoji 应该依次是 {' '.join(EMOJIS)}")
    if not case.suspect.confession:
        problems.append("缺少 suspect.confession")
    if not case.suspect.stolen:
        problems.append("缺少 suspect.stolen（被盗物的叫法）")
    if len(case.briefing) > 130:
        problems.append(f"briefing 太长（{len(case.briefing)} 字），要压到 110 字左右")
    for c in case.claims:
        if len(c.text) > 34:
            problems.append(f"证词 {c.id} 太长（{len(c.text)} 字）")
    return problems


def extract_yaml(raw: str) -> str:
    m = re.search(r"```(?:yaml)?\s*\n(.*?)```", raw, re.S)
    return (m.group(1) if m else raw).strip() + "\n"


def check(text: str) -> list[str]:
    try:
        case = parse_case(yaml.safe_load(text))
    except (yaml.YAMLError, CaseFormatError) as e:
        return [f"YAML 无法解析：{e}"]
    return [p.message for p in validate(case)] + design_problems(case)


async def main(case_id: str, idea: str) -> None:
    llm = OpenAICompatLLM(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"], temperature=0.8)
    example = EXAMPLE.read_text(encoding="utf-8")
    messages = [{"role": "user", "content": PROMPT.format(case_id=case_id, idea=idea, example=example)}]
    out = ROOT / "cases" / "drafts" / f"{case_id}.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    for round_ in range(MAX_ROUNDS + 1):
        raw = await llm.complete(MODEL, messages, timeout=600)
        text = extract_yaml(raw)
        out.write_text(text, encoding="utf-8")
        problems = check(text)
        print(f"第 {round_ + 1} 稿：{len(problems)} 个问题")
        for p in problems:
            print(f"  - {p}")
        if not problems:
            print(f"初稿通过校验：{out.relative_to(ROOT)}。下一步：自对弈，再人工审读。")
            break
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": FIX.format(problems="\n".join(f"- {p}" for p in problems))},
        ]
    else:
        print(f"改了 {MAX_ROUNDS} 轮还有问题，初稿留在 {out.relative_to(ROOT)}，需要人工处理。")
    await llm.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
