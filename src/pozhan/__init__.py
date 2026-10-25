"""《破绽》：在灵矽语音设备上审讯 AI 嫌疑人的侦探游戏。

模块划分见 Design Issue #4：

- case      案件数据：证词、线索卡、矛盾表、档位
- engine    审讯规则：纯函数式状态机，不调用大模型
- intent    意图解析：玩家原话 → 事件
- director  台词生成：结果 → 旁白 + 嫌疑人台词
- llm       OpenAI 兼容的大模型客户端
- session   会话识别与状态存储
- game      一轮对话的编排
- server    灵矽接入层（OpenAI 兼容接口）
"""
