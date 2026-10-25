# 《破绽》

在灵矽语音设备上玩的侦探游戏：几个人（或一个人）围着设备，**亲口审问一个会撒谎的 AI 嫌疑人**，拍出线索卡戳破他的证词，直到他崩溃认罪。

- 不用看屏幕，全程语音。
- 1–N 人合作，一局 10–15 分钟。
- 嫌疑人由大模型扮演，会狡辩、圆谎、慌乱、说漏嘴；输赢由程序判定，大模型骗不了你，你也骗不了它。

## 怎么玩

1. 打印线索卡（见下文），摆在桌上。
2. 对设备说「开始审讯」，听案情和嫌疑人的开场证词。
3. 随便提问，找证词里的破绽。**证词会越审越多**：问到关键的事，他会说出新的证词；被戳破后，他会改口编出新的谎话。证词按说出口的顺序编号。
4. 拍出一张卡，说「用二号卡反驳证词一」，或者直接说「看这张，电梯监控拍到你九点半上了十八楼」。
5. 戳穿全部证词就破案。出示错三次，或者审讯超过十五分钟，律师就会到场，你们输了。
   - 有的卡和证词沾边、但不够硬：出示了不扣次数，嫌疑人会搪塞过去。
   - 只是在提问里提到卡的内容、没有明确出示：驳不倒也不扣次数。

随时可以说：「念一下证词」「念一下三号卡」「还有几次机会」「给点提示」「规则」「再说一遍」「重新开始」「下一个案子」「有哪些案子」「讲讲真相」「结束游戏」。

破案后会按失误评级（S/A/B/C）。第一次玩会先进入三分钟的新手教学关。

一页纸的玩家须知见 [docs/players.md](docs/players.md)。

**陪玩屏（可选）**：在电视或平板上打开 `服务地址/screen?token=…`，就有一块随对局实时更新的只读大屏，显示证词状态、心理防线、律师倒计时和字幕；戳破证词时会全屏强调。配置方法见[上线指南](docs/deploy.md#陪玩屏可选)。

**网页开玩（可选）**：没有灵矽硬件时，打开 `服务地址/screen?play=1&token=…`，按住按钮说话就能玩，语音识别和情感语音照样走灵矽。见[上线指南](docs/deploy.md#网页开玩可选)。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync
```

```bash
uv run pozhan cards cases/golden-watch.yaml -o cards.html
```

用浏览器打开 `cards.html` 打印（A4，一页四张）。

```bash
LLM_BASE_URL=https://你的-openai-兼容地址/v1 LLM_API_KEY=你的密钥 POZHAN_API_KEY=自己定一个 uv run pozhan serve
```

服务启动后对外提供 OpenAI 兼容的 `/v1/chat/completions`。接入灵矽设备的完整步骤见 **[上线指南](docs/deploy.md)**。

不配置 `LLM_BASE_URL` / `LLM_API_KEY` 也能启动：规则照常判定，但嫌疑人只会说几句固定台词，只适合调试流程。

## 配置

全部通过环境变量配置。

| 变量 | 说明 | 默认值 |
|---|---|---|
| `POZHAN_API_KEY` | 接口密钥。灵矽「我的模型」里的「API密钥」填同一个值。**上线必须设置** | 空（不校验） |
| `POZHAN_SCREEN_TOKEN` | 陪玩屏的只读令牌，打开 `/screen?token=…` 时使用 | 空（不校验） |
| `POZHAN_LINX_DEVICE` | 网页开玩用的灵矽虚拟设备身份文件（`tools/devsim.py ota` 生成的 `.data/devsim.json`） | 空（不开放网页开玩） |
| `LLM_BASE_URL` / `LLM_API_KEY` | 大模型的 OpenAI 兼容接口 | 空 |
| `INTENT_MODEL` | 意图分类模型：判断玩家是不是在出示线索卡 | `doubao-seed-2.0-mini` |
| `SUSPECT_MODEL` | 嫌疑人台词模型 | `deepseek/deepseek-v4.1-flash` |
| `LLM_EXTRA_BODY` | 附加到每次模型请求的 JSON | `{"thinking": {"type": "disabled"}}`（关闭思考，降低延迟） |
| `POZHAN_CASES` | 案件库目录，顺序见目录里的 `index.txt` | `cases` |
| `POZHAN_CASE` | 只玩这一个案件文件（调试、评测用），设置后不加载案件库 | 空 |
| `POZHAN_LOG_DIR` | 日志目录（对局日志在 `games/` 下） | `logs` |
| `POZHAN_LOG_REQUESTS` | 设为 `1` 时记录平台发来的原始请求（不含鉴权头） | 关闭 |
| `HOST` / `PORT` | 监听地址和端口 | `127.0.0.1` / `8000` |

## 写一个新案件

案件是一个 YAML 文件，放在 `cases/` 目录下，格式参考 [cases/golden-watch.yaml](cases/golden-watch.yaml)。内容包括：案情、嫌疑人的人设、真相和认罪内容、证词、线索卡、矛盾表、间接证据和档位。

- **证词的 `unlock`**：写 `topic` 和 `examples`，就要问到这个话题才会说出口；只写 `after`，就是这条证词被戳破后改口说出的新谎话。
- **`weak`**：沾边但驳不倒的卡，出示时不扣次数。
- **顺序**：写在 `cases/index.txt` 里，决定「开始审讯」和「下一个案子」的顺序。

推荐用流水线出初稿，再人工打磨：

```bash
uv run python tools/draft_case.py my-case "一两句话的核心诡计和背景"   # 初稿写到 cases/drafts/
uv run pozhan check cases/drafts/my-case.yaml                         # 校验
POZHAN_CASE=cases/drafts/my-case.yaml uv run python evals/selfplay.py 10   # AI 自对弈：能不能破、会不会编造
```

人工审读、改好以后，再移到 `cases/` 下并加进 `index.txt`。

校验器会检查：每条谎言恰好有一张卡能戳破；至少有一张干扰卡；隐藏证词的解锁链条完整、话题不重复、例句够用；间接证据不能同时是能戳破的卡；每条矛盾都有失言提示，等等。

## 开发

```bash
uv run pytest
```

```bash
uv run ruff check
```

- 架构：模块划分与接口契约见设计 Issue #4。`engine` 是纯规则状态机，只有 `intent` 和 `director` 调用大模型。
- 评测：在 `evals/` 下，需要真实模型。
  - `intent_eval.py`：意图解析准确率；
  - `suspect_eval.py`：嫌疑人台词与诱供话术；
  - `play_latency.py`：整局每轮时延。
- 端到端：`tools/devsim.py` 用软件冒充一台灵矽设备，用合成语音打一局，用法见文件开头的说明。

协作流程见 [AGENTS.md](AGENTS.md)。
