"""台词生成：把规则引擎的结果变成这一轮要说的话。

旁白用模板（零延迟），嫌疑人台词由大模型生成并经过守卫检查（Proposal #3 决策 3/6）。
"""

from pozhan.director.director import Director, Line

__all__ = ["Director", "Line"]
