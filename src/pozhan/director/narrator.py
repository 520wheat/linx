"""旁白台词：全部用模板，零延迟、确定性。

只有一个音色（#4 风险 R4），旁白一律用第三人称叙述，和嫌疑人的第一人称区分开。
"""

from pozhan.case.model import Case
from pozhan.engine.state import Interrogation

CN = "零一二三四五六七八九十"
AGAIN = "说「重新开始」可以再来一局。"


def cn(n: int) -> str:
    """把数字读成中文，避免 TTS 把「1」读成「幺」等。"""
    if 0 <= n <= 10:
        return CN[n]
    if n < 20:
        return "十" + CN[n - 10]
    if n < 100:
        return CN[n // 10] + "十" + (CN[n % 10] if n % 10 else "")
    return str(n)


def duration(seconds: int) -> str:
    minutes, sec = divmod(max(0, seconds), 60)
    if minutes and sec:
        return f"{cn(minutes)}分{cn(sec)}秒"
    return f"{cn(minutes)}分钟" if minutes else f"{cn(sec)}秒"


def rules(case: Case) -> str:
    n = len(case.cards)
    return (
        f"规则很简单：你们可以随便提问，发现证词的破绽，就说用几号卡反驳第几条证词。"
        f"你们手里有{cn(n)}张线索卡，其中有的卡帮不上忙。"
        f"出示错{cn(case.limits.strikes)}次，或者审讯超过{cn(case.limits.minutes)}分钟，律师就会到场。"
        f"想听证词就说「念一下证词」，想听卡就说「念一下几号卡」。"
    )


def briefing(case: Case) -> str:
    return case.briefing


def opening_statement(case: Case) -> str:
    """嫌疑人的开场陈述，逐字使用案件里的证词，保证玩家听到的证词和规则一致。

    隐藏证词不在开场说（#46）；证词按说出口的顺序编号。
    """
    parts = [f"第{cn(i)}，{c.text}" for i, c in enumerate(case.opening_claims, 1)]
    return "警官，我配合调查。" + "".join(parts)


def read_claims(case: Case, state: Interrogation) -> str:
    lines = []
    for i, claim_id in enumerate(state.revealed, 1):
        c = case.claim(claim_id)
        mark = "（已被戳破）" if claim_id in state.broken else ""
        lines.append(f"证词{cn(i)}{mark}：{c.text.rstrip('。！？.!?')}")
    return "。".join(lines) + "。"


def new_claim(label: int) -> str:
    """嫌疑人说出一条新证词之后，旁白把它记下来（#46）。"""
    return f"记下了，这是证词{cn(label)}。"


def amended(case: Case, claim_id: int, label: int) -> str:
    """戳破之后嫌疑人改口，旁白逐字复述新说法，保证玩家记下的证词和规则一致。"""
    return f"他改口了：{case.claim(claim_id).text}这是证词{cn(label)}。"


def read_card(case: Case, card_id: int) -> str:
    card = case.card(card_id)
    return f"{cn(card.id)}号卡，{card.title}：{card.text}" if card else ""


# 出示后旁白先宣布判定、嫌疑人再反应：判定是模板，玩家几乎立刻就能听到结果（#22）


def broke(claim_id: int) -> str:
    return f"证词{cn(claim_id)}被戳破了！"


def still_holding(case: Case, state: Interrogation) -> str:
    # 不按真假筛选：列出来的只是「说出口、还没被戳破」的证词，不能借此泄露哪条是真话
    left = [i for i, claim_id in enumerate(state.revealed, 1) if claim_id not in state.broken]
    if left:
        return f"他还在坚持{'、'.join(f'证词{cn(i)}' for i in left)}。"
    # 说出口的都戳破了却还没认罪：还有话没问出来（#46）。不说还剩几条，只提示该做什么
    return "他说过的证词都被戳破了，可还没松口。看看手里还没用上的卡，围绕它追问。"


def wrong(claim_id: int) -> str:
    return f"这张卡驳不倒证词{cn(claim_id)}。"


def weak(claim_label: int) -> str:
    return f"这张卡说明了点什么，但还不够硬，驳不倒证词{cn(claim_label)}。这次不算出示错误。"


def countdown(strikes_left: int) -> str:
    return f"律师还有{cn(strikes_left)}次就到。"


def already_broken(claim_id: int) -> str:
    return f"证词{cn(claim_id)}已经被戳破了，看看别的证词吧。"


def unknown_ref(case: Case, state: Interrogation, card: int | None, claim: int | None) -> str:
    if card is not None:
        return f"你们手里没有{cn(card)}号卡，线索卡是一到{cn(len(case.cards))}号。"
    return f"没有第{cn(claim)}条证词，他到现在只说过{cn(len(state.revealed))}条。"


def clarify(card: int | None, claim: int | None) -> str:
    if card is not None:
        return f"你想用{cn(card)}号卡反驳第几条证词？"
    if claim is not None:
        return f"你想用几号卡反驳证词{cn(claim)}？"
    return "你想用几号卡，反驳第几条证词？"


def remaining(strikes_left: int, seconds_left: int) -> str:
    return f"还能出示错{cn(strikes_left)}次，审讯时间还剩{duration(seconds_left)}。"


def confession_wrap(case: Case) -> str:
    return f"案件告破！真相是：{case.reveal}{AGAIN}"


def lawyer(case: Case, reason: str) -> str:
    why = "出示错得太多，" if reason == "strikes" else "审讯时间到了，"
    return f"{why}{case.suspect.name}的律师到了，他不会再开口了。真相是：{case.reveal}{AGAIN}"


def quit_game(case: Case) -> str:
    return f"游戏结束。真相是：{case.reveal}{AGAIN}"


def not_heard() -> str:
    return "刚才没听清，能再说一遍吗？"


def game_over() -> str:
    return f"这一局已经结束了。{AGAIN}"
