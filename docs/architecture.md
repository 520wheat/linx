# 《破绽》架构说明

黑客松交付文档。说明模块如何拆分、如何协作、三人如何并行。实现以仓库代码为准。

## 1. 目标与边界

玩家用语音审问嫌疑人，出示线索卡戳破不在场证明。

- **规则引擎判定输赢**（戳破全部谎言 / 出示错误三次 / 十五分钟律师到场）。
- **大模型不判案**，只做两件事：把玩家原话解析成事件，以及按本轮裁定生成口语台词。
- 本期不做开放世界推理、不做多实例共享对局。模型失败时走兜底台词，规则仍然有效。

## 2. 运行时链路

```
玩家语音
  → 灵矽（ASR / 多情感 TTS）
  → POST /v1/chat/completions（OpenAI 兼容，model=pozhan）
  → Game：intent → engine → director
  → SSE 流式回复（首字 emoji 驱动灵矽音色）
  → ScreenHub 推陪玩屏

网页开玩 /screen?play=1：
浏览器 PCM ⇄ WS /screen/voice ⇄ Opus ⇄ 灵矽设备协议
之后仍回到 /v1。
```

会话在进程内 `MemoryStore`，按设备隔离。平台聊天历史作废，服务端自管最近 8 轮。

## 3. 模块协作

```
case YAML ──► Game ◄── session（每设备一局）
                │
     玩家原话 ──► intent ──► Event
                │              │
                │              ▼
                │           engine.apply(state, event) → (state, Outcome)
                │              │
                │              ▼
                └──► director.speak(Outcome) → Line（旁白/嫌疑人）
                       │
                       ├──► server 流式写出
                       └──► screen 快照（结局前不剧透）
```

只有 `intent`、`director` 调用 `llm`。`engine` 是纯函数，不进网络。

## 4. 模块规格

| 模块 | 代码 | 职责 | 输入 | 输出 | 禁区 |
|---|---|---|---|---|---|
| case | `src/pozhan/case` | 加载并校验案件 | YAML | 证词、线索卡、矛盾表、档位 | 不跑对局 |
| intent | `src/pozhan/intent` | 原话 → 事件 | 文本 | `Ask` / `Present` / `Command` | 不改状态。先规则，未命中再分类模型 |
| engine | `src/pozhan/engine` | 审讯状态机 | `Event` + `Interrogation` | 新状态 + `Outcome` | 不调模型；输赢、升档、认罪只在这里 |
| director | `src/pozhan/director` | 台词 | `Outcome` + 案件 + 历史 | 流式 `Line` | 不判案。守卫禁止提前认罪、编造新不在场证明 |
| game | `src/pozhan/game.py` | 编排一轮 | 一句话 | 流式 `Line` | 不碰 HTTP |
| server | `src/pozhan/server` | 对外协议 | HTTP / WS | `/v1`、`/screen`、`/healthz` | 不写玩法 |
| session | `src/pozhan/session` | 对局存储 | 设备标识 | `Session` | 不解析意图 |
| screen | `src/pozhan/screen` | 陪玩屏 / 网页开玩 | 快照 | HTML + SSE | 结局前不含真相 |
| voice | `src/pozhan/voice` | 网页充当灵矽设备 | PCM | Opus 上行 / PCM 下行 | 一设备同时只服务一个网页玩家 |
| llm | `src/pozhan/llm` | OpenAI 兼容客户端 | 消息列表 | 流式文本 | 不感知案件 |

案件在 `cases/`，顺序 `cases/index.txt`。打印卡：`uv run pozhan cards <案件.yaml>`。

## 5. 关键数据与接口契约

- **Event**：`Ask`（提问，可带隐藏证词 topic）、`Present`（出示 card 反驳第 claim 条已说证词）、`Command`（开始审讯、提示、下一案等口令）。
- **Interrogation**：已揭示证词、已戳破证词、心理档位、剩余错误次数、律师倒计时、阶段。
- **Outcome**：`Briefing` / `Answer` / `Revealed` / `Broke` / `Wrong` / `Weak` / `Confession` / `Lawyer` 等，导演只根据它说话。
- **Line**：`narrator` 或 `suspect` 的一句对外台词。

核心调用：

```
engine.apply(state: Interrogation, event: Event) -> (Interrogation, Outcome)
Interpreter.parse(text, state) -> Event | Clarify
Director.speak(case, state, outcome, history) -> AsyncIterator[Line]
Game.play(session, text) -> AsyncIterator[Line]
```

对外 HTTP（鉴权：`POZHAN_API_KEY` / 陪玩屏 `POZHAN_SCREEN_TOKEN`，空则本地不校验）：

| 路径 | 用途 |
|---|---|
| `POST /v1/chat/completions` | 灵矽「我的模型」入口，SSE |
| `GET /healthz` | 存活与当前案件 |
| `GET /screen` | 只读陪玩屏；`?play=1` 网页开玩 |
| `GET /screen/state` `GET /screen/events` | 快照与推送 |
| `WS /screen/voice` | 网页 ↔ 灵矽中转 |

## 6. 分工

三人按模块并行，不按「各写一页界面」。交叉口在 `game.py`：案件 YAML 由玩法引擎定稿，陪玩屏只展示已揭示信息。

| 轨道 | 谁 | 范围 | 不碰 |
|---|---|---|---|
| 玩法引擎 | rwf | `engine`、`intent`、`director` 守卫、`cases/` 四案与校验 | HTTP、灵矽握手、大屏样式 |
| 灵矽接入 | 520wheat | `server` `/v1`、鉴权、`session`、`voice`、智控台与本地部署 | 改输赢规则、改矛盾表 |
| 陪玩屏与演示 | 小组共同，文档由 520wheat 收口 | `screen`、线索卡、README / 本文件、demo 录像 | 改判定逻辑 |

提交记录可核对：`rwf` 落地主干与案件；`520wheat` 合入 PR 并维护仓库与交付文档。第三轨若另有组员，在对应 `screen` / 录像提交里署名即可。

## 7. 明确不做

- 矛盾表写死，模型不得新造不在场证明或新证人。
- 不做 Redis 多实例对局。
- 大模型缺省或失败：规则照常，嫌疑人只说兜底台词。
