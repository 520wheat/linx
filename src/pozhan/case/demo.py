"""骨架阶段使用的最小案件，等 #6 的 YAML 加载器完成后删除。"""

from pozhan.case.model import Card, Case, Claim, Contradiction, Stage, Suspect

DEMO_CASE = Case(
    id="demo",
    title="骨架演示",
    briefing="这是骨架阶段的演示案件。",
    suspect=Suspect(name="林志远", persona="行政主管"),
    claims=(Claim(1, "我一直在包厢。", lie=True),),
    cards=(Card(1, "电梯监控", "他上过楼。"), Card(2, "点歌记录", "包厢没人点歌。")),
    contradictions=(Contradiction(card=1, claim=1, concession="承认上过楼。"),),
    stages=(Stage("镇定", "😌", "从容"), Stage("崩溃", "😭", "崩溃")),
    reveal="演示结束。",
)
