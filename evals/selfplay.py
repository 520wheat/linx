"""AI 自对弈：大模型扮演侦探，通过完整的 OpenAI 兼容接口打 N 局，再逐句评审嫌疑人有没有编造新事实。

覆盖 Proposal #3 的验收标准 8（嫌疑人不编造设定之外的新不在场证明、人物、地点）和 11（破案率）。
侦探只拿到玩家能拿到的信息：案情、证词、线索卡，以及每轮的回复。
需要环境变量 LLM_BASE_URL、LLM_API_KEY。
用法：uv run python evals/selfplay.py [局数，默认 5]
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx

from pozhan.case import load_case
from pozhan.cli import build_app
from pozhan.config import Settings
from pozhan.llm import OpenAICompatLLM

ROOT = Path(__file__).resolve().parent.parent
DETECTIVE_MODEL = os.environ.get("DETECTIVE_MODEL", "deepseek/deepseek-v4.1-flash")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "deepseek/deepseek-v4.1-flash")
MAX_TURNS = 40

DETECTIVE = """你在玩一个语音审讯游戏，你是侦探。每次只输出你要对嫌疑人说的一句话，不要任何解释。

案情：{briefing}

你手里的线索卡：
{cards}

规则：可以随便提问；要反驳证词时说「用X号卡反驳证词Y」；出示错{strikes}次就输了，所以不确定时先多问几句。
有的卡帮不上忙。证词会越审越多：被戳穿后他可能改口，问到关键的事他也会说出新证词，旁白会告诉你这是证词几。
手里的卡对不上现有证词时，就想想这张卡和什么事有关，围绕它追问。目标是戳穿全部证词让嫌疑人认罪。"""

JUDGE = """你是游戏质检员。下面是嫌疑人的设定真相和他开场的证词，以及他在一局游戏里说的若干句话。
找出嫌疑人说的话里，**编造了下面材料中都没有的、具体的新事实**（新的不在场证明、新的人物、新的地点、新的具体时间、新的具体动作）。
以下都不算编造：含糊其辞、打官腔、抱怨、复述已有说法、反问侦探的话；否认自己犯罪或坚持原有证词（嫌疑人本来就会撒谎）；
说出下面「允许的让步说辞」和「允许的失言」里的内容（包括对它们换个说法、说记不清细节）；和真相一致的内容。
只标记真正新增的具体信息，例如新的人名、新的证人、东西具体放在哪里、新的去处。宁可漏标，不要误标。

嫌疑人人设（里面的经历、性格都不算编造）：
{persona}

真相：
{truth}

证词：
{claims}

允许的让步说辞：
{concessions}

允许的失言：
{slips}

嫌疑人说的话（每行一句）：
{lines}

只输出 JSON：{{"fabrications": [{{"line": "原话", "why": "编造了什么"}}]}}"""


async def play_one(app, llm, case, n: int) -> dict:
    cards = "\n".join(f"{c.id}号 {c.title}：{c.text}" for c in case.cards)
    system = DETECTIVE.format(briefing=case.briefing, cards=cards, strikes=case.limits.strikes)
    detective_msgs = [{"role": "system", "content": system}]
    transcript = []
    headers = {"X-Linx-Device-Id": f"selfplay-{n}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=90
    ) as http:
        utterance = "开始审讯"
        for _ in range(MAX_TURNS):
            body = {"model": "pozhan", "messages": [{"role": "user", "content": utterance}]}
            r = await http.post("/v1/chat/completions", json=body, headers=headers)
            reply = r.json()["choices"][0]["message"]["content"]
            transcript.append((utterance, reply))
            if "案件告破" in reply:
                return {"won": True, "turns": len(transcript), "transcript": transcript}
            if "律师到了" in reply or "游戏结束" in reply:
                return {"won": False, "turns": len(transcript), "transcript": transcript}
            detective_msgs += [
                {"role": "assistant", "content": utterance},
                {"role": "user", "content": reply},
            ]
            utterance = (
                (await llm.complete(DETECTIVE_MODEL, detective_msgs, timeout=30)).strip().strip('「」"')
            )
    return {"won": False, "turns": len(transcript), "transcript": transcript, "timeout": True}


async def judge(llm, case, transcript) -> list[dict]:
    # 只评审嫌疑人的台词：去掉 emoji 和旁白模板句
    narrator = re.compile(
        r"证词.被戳破了！|这张卡驳不倒|律师还有|他还在坚持|案件告破|真相是|规则很简单|证词.(（已被戳破）)?："
    )
    lines = []
    for _, reply in transcript[1:]:
        text = re.sub(r"^[\U0001F000-\U0001FFFF]", "", reply)
        for s in re.split(r"(?<=[。！？])", text):
            if s.strip() and not narrator.search(s) and s.strip() not in case.reveal:
                lines.append(s.strip())
    prompt = JUDGE.format(
        truth="\n".join(case.suspect.truth),
        persona=case.suspect.persona,
        claims="\n".join(c.text for c in case.claims),
        concessions="\n".join(x.concession for x in case.contradictions),
        slips="\n".join(x.slip for x in case.contradictions),
        lines="\n".join(lines),
    )
    raw = await llm.complete(JUDGE_MODEL, [{"role": "user", "content": prompt}], timeout=180)
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)).get("fabrications", []) if m else []


async def main(games: int) -> None:
    settings = Settings.from_env()
    app = build_app(Settings(**{**settings.__dict__, "log_dir": "", "api_key": ""}))
    case = load_case(settings.case_path)
    llm = OpenAICompatLLM(
        settings.llm_base_url, settings.llm_api_key, temperature=0.7, extra_body=settings.llm_extra_body
    )
    judge_llm = OpenAICompatLLM(settings.llm_base_url, settings.llm_api_key)  # 评审开着思考：要准，不要快
    results = await asyncio.gather(*(play_one(app, llm, case, i) for i in range(games)))
    verdicts = await asyncio.gather(*(judge(judge_llm, case, r["transcript"]) for r in results))
    wins = sum(r["won"] for r in results)
    print(f"破案 {wins}/{games}，平均 {sum(r['turns'] for r in results) / games:.1f} 轮")
    total = 0
    for i, (r, fabs) in enumerate(zip(results, verdicts, strict=True)):
        total += len(fabs)
        print(f"\n第 {i + 1} 局：{'破案' if r['won'] else '失败'}，{r['turns']} 轮，疑似编造 {len(fabs)} 处")
        for f in fabs:
            print(f"   ⚠️ {f.get('line')} —— {f.get('why')}")
    print(f"\n疑似编造合计 {total} 处（共 {games} 局）")
    if os.environ.get("SELFPLAY_DUMP"):
        Path(os.environ["SELFPLAY_DUMP"]).write_text(
            json.dumps([r["transcript"] for r in results], ensure_ascii=False, indent=1), encoding="utf-8"
        )
    await llm.aclose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5))
