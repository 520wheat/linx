# 《破绽》

在灵矽语音设备上玩的侦探游戏：几个人（或一个人）围着设备，**亲口审问一个会撒谎的 AI 嫌疑人**，拍出线索卡戳破他的证词，直到他崩溃认罪。

- 不用看屏幕，全程语音。
- 1–N 人合作，一局 10–15 分钟。
- 嫌疑人由大模型扮演，会狡辩、圆谎、慌乱、说漏嘴；输赢由程序判定，大模型骗不了你，你也骗不了它。

## 怎么玩

1. 打印线索卡（见下文），摆在桌上。
2. 对设备说「开始审讯」，听案情和嫌疑人的三条证词。
3. 随便提问，找证词里的破绽。
4. 拍出一张卡，说「用二号卡反驳证词一」，或者直接说「电梯监控拍到你九点半上了十八楼」。
5. 戳穿全部证词就破案。出示错三次，或者审讯超过十五分钟，律师就会到场，你们输了。

随时可以说：「念一下证词」「念一下三号卡」「还有几次机会」「再说一遍」「重新开始」「结束游戏」。

一页纸的玩家须知见 [docs/players.md](docs/players.md)。

**陪玩屏（可选）**：在电视或平板上打开 `服务地址/screen?token=…`，就有一块随对局实时更新的只读大屏，显示证词状态、心理防线、律师倒计时和字幕；戳破证词时会全屏强调。配置方法见[上线指南](docs/deploy.md#陪玩屏可选)。

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
| `LLM_BASE_URL` / `LLM_API_KEY` | 大模型的 OpenAI 兼容接口 | 空 |
| `INTENT_MODEL` | 意图分类模型：判断玩家是不是在出示线索卡 | `doubao-seed-2.0-mini` |
| `SUSPECT_MODEL` | 嫌疑人台词模型 | `deepseek/deepseek-v4.1-flash` |
| `LLM_EXTRA_BODY` | 附加到每次模型请求的 JSON | `{"thinking": {"type": "disabled"}}`（关闭思考，降低延迟） |
| `POZHAN_CASE` | 案件文件 | `cases/golden-watch.yaml` |
| `POZHAN_LOG_DIR` | 日志目录（对局日志在 `games/` 下） | `logs` |
| `POZHAN_LOG_REQUESTS` | 设为 `1` 时记录平台发来的原始请求（不含鉴权头） | 关闭 |
| `HOST` / `PORT` | 监听地址和端口 | `127.0.0.1` / `8000` |

## 写一个新案件

案件是一个 YAML 文件，格式参考 [cases/golden-watch.yaml](cases/golden-watch.yaml)，包括案情、嫌疑人人设与真相、证词、线索卡、矛盾表和档位。写完先校验：

```bash
uv run pozhan check cases/你的案件.yaml
```

校验器会检查：每条谎言恰好有一张卡能戳破、至少有一张干扰卡、档位数等于矛盾数加一、每条矛盾都有失言提示，等等。

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
