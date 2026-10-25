# 上线指南

把《破绽》部署成一个公网可访问的服务，再让灵矽智能体把它当作「大模型」来调用。整体链路：

```
灵矽设备 ──语音──▶ 灵矽平台（ASR / TTS / 情绪音色）──OpenAI 兼容请求──▶ 破绽服务 ──▶ 大模型
```

## 1. 部署服务

### Docker（推荐）

```bash
docker build -t pozhan .
```

```bash
docker run -d --name pozhan -p 8000:8000 -v pozhan-data:/data -e POZHAN_API_KEY=换成一个足够长的随机串 -e LLM_BASE_URL=https://你的-openai-兼容地址/v1 -e LLM_API_KEY=你的大模型密钥 pozhan
```

```bash
curl http://127.0.0.1:8000/healthz
```

返回 `{"ok":true,"case":"golden-watch"}` 就说明服务起来了。

- **对局日志**：在卷 `/data/logs/games/<日期>/` 下，每局一个 JSONL 文件。
- **服务器网卡 MTU 小于 1500 时（很多云主机是 1450、1480），给容器单独建一个同 MTU 的网络**，否则从容器出去的 TLS 握手会偶发卡死：大模型调用报 `ConnectTimeout`，网页开玩报「连接灵矽失败」。先用 `ip -o link` 看出口网卡的 MTU，再按它建网络。同时把 DNS 换成稳定的公共解析，并让 A/AAAA 查询依次发出，避免偶发的 5 秒解析延迟：

  ```bash
  docker network create --opt com.docker.network.driver.mtu=1480 pozhan-net
  docker run -d --name pozhan --restart unless-stopped --network pozhan-net -p 127.0.0.1:18787:8000 \
    --dns 223.5.5.5 --dns 119.29.29.29 --dns-opt single-request-reopen --dns-opt timeout:1 --dns-opt attempts:3 \
    --env-file /opt/pozhan/env -v /opt/pozhan/data:/data pozhan
  ```

  以上两个坑都是在 las 上实测踩到的（出口网卡 MTU 1480，Docker 网桥默认 1500）。
- **换案件**：镜像里自带 `cases/` 案件库（顺序见 `cases/index.txt`）。要用自己的案件库，就挂载一个目录，并设置 `POZHAN_CASES` 指向它；只想玩某一个案件时，设置 `POZHAN_CASE` 指向那个文件。

### 直接运行

```bash
uv sync --no-dev
```

```bash
HOST=0.0.0.0 PORT=8000 POZHAN_API_KEY=... LLM_BASE_URL=... LLM_API_KEY=... uv run pozhan serve
```

## 2. 提供公网 HTTPS 地址

灵矽平台在公网上，必须能通过 HTTPS 访问到服务。

- **正式上线**：放在有固定域名和证书的反向代理后面（Nginx、云厂商负载均衡等）。Nginx 要注意两点：
  - `/screen/voice` 是 WebSocket，要转发 `Upgrade` / `Connection` 头；
  - 其余路径要关闭缓冲（`proxy_buffering off`），陪玩屏的 SSE 和「我的模型」的流式回复才能实时到达。
- **两套智能体**：建议在智控台建两个智能体，各配一个「我的模型」。本地测试用的指向临时隧道，线上用的指向正式域名，网页开玩各用一台虚拟设备（`DEVSIM_STATE` 指定不同的身份文件），互不干扰。
- **临时演示**：用 cloudflared 的临时隧道。如果本机有代理导致 QUIC 连不上，加 `--protocol http2`。

```bash
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

隧道启动后会打印一个 `https://xxxx.trycloudflare.com` 地址，下面称为「服务地址」。

## 3. 在灵矽智控台接入

登录 [智控台](https://xrobo.qiniu.com)。

### 3.1 添加自定义模型

进入「LLM → 我的模型 → 新增模型」，按下表填写，然后保存：

| 字段 | 填写 |
|---|---|
| 名称 | 随意，例如「破绽」 |
| 接口类型 | OpenAI接口 |
| API Base URL | `服务地址/v1`，例如 `https://xxxx.trycloudflare.com/v1` |
| 系统推理模型 | `pozhan` |
| API密钥 | 与服务端 `POZHAN_API_KEY` **相同的值**。⚠️ **不能留空**，留空时平台会在设备握手后立即断开连接 |

### 3.2 配置智能体

进入「智能体管理」，新建一个智能体，在「配置角色」里设置：

| 配置项 | 建议值 | 原因 |
|---|---|---|
| 大语言模型 | 自定义模型 → 上一步添加的模型 | 由破绽服务接管对话 |
| 角色音色 | 带「（多情感）」的音色，例如「爽快思思（多情感）」 | 嫌疑人的语气需要随心理档位变化 |
| 多情绪变化 | 开启 | 让回复开头的 emoji 驱动音色情绪 |
| 空闲超时（对话与视觉） | 600 秒以上 | 玩家讨论时可能很久不说话 |
| 记忆 | 无记忆 | 对局状态和对话历史由服务端自己维护 |
| 意图识别（技能与扩展） | 无意图识别，或统一意图识别 | 「分离意图识别」会额外调用一次模型，会被当成玩家的一句话 |
| 角色介绍 | 随意 | 服务端不使用 |

保存配置。按平台提示，**改完配置要重启设备才会生效**。

### 3.3 绑定设备

在该智能体的「设备管理 → 新增」里，输入设备播报的 6 位验证码。

## 4. 验收

- **真机**：对设备说「开始审讯」，应该听到案情、嫌疑人的开场证词和一句话玩法（约三十秒）。
- **没有硬件**：用设备模拟器，在 macOS 上用合成语音跑一局：

```bash
uv run --group devsim python tools/devsim.py ota
```

第一次运行会打印激活码，到「设备管理 → 新增」填入，然后再运行一次 `ota`。

```bash
uv run --group devsim python tools/devsim.py play scripts/win.txt
```

模拟器会打印每轮的识别结果、回复和时延（从说完到首个音频）。

## 陪玩屏（可选）

陪玩屏是一块只读的大屏网页，跟着语音对局实时更新，适合电视、平板或路演投影。所有操作仍然靠语音。

1. 服务端设置只读令牌（和接口密钥 `POZHAN_API_KEY` 分开；没开网页开玩时，泄露了也只能看、不能操作）：`-e POZHAN_SCREEN_TOKEN=换成一个随机串`。
2. 在电视或电脑浏览器里打开 `服务地址/screen?token=<POZHAN_SCREEN_TOKEN>`，全屏显示即可。
   - 默认显示**最近活跃的一局**。同时有多台设备时，在链接后面加上 `&device=<设备 MAC>`。
   - 强调色可以用 `&accent=sage` / `mist` / `amber` 切换，默认是珊瑚色。
3. 画面会随对局自动切换：开局 → 审讯中 → 戳破瞬间（3 秒）→ 结局。

**数据更新方式**：页面优先用 SSE 接收推送。如果 4 秒内一条推送都没收到，会自动改为每 0.8 秒轮询一次状态。原因是 **Cloudflare 临时隧道（trycloudflare）不支持 SSE**，有些代理也会缓冲流式响应。在固定域名和普通反向代理下，SSE 照常工作；用 Nginx 做反向代理时，`/screen/events` 需要关闭缓冲（服务端已经带了 `X-Accel-Buffering: no` 响应头）。

## 网页开玩（可选）

没有灵矽硬件也能玩：打开 `服务地址/?token=<POZHAN_SCREEN_TOKEN>`。

- 点一下「开始游戏」：授权麦克风，案子直接开始。之后**不用再按按钮**（#64）：
  - 嫌疑人一说完，麦克风自动开始听，直接开口问就行；说完停一下就会自动发送。
  - 只在对方说完之后才听，外放的声音不会被当成玩家说的话。
  - 他说话时点一下状态球，可以打断他。
  - 两分钟没人说话，或者页面切到后台，会自动暂停，点一下继续。
  - 电脑上也可以按住空格说话。
- **出示**：把线索卡拖到证词上；也可以点卡、再点证词。选中卡时，还能反驳的证词会亮起来。
- 底部只有一句情境提示：刚开局教提问，第一次出示前教拖卡，卡住一分多钟提醒说「给点提示」。
- 手机竖屏时，画面下方是台词、证词和横向的手牌。
- 没有麦克风权限时，才会出现打字框。

拖卡和打字也走灵矽（设备协议的 `listen detect`，见 #59），识别和嫌疑人的情感语音都和真机一致；没有麦克风也能玩。

原理：网页充当一台灵矽设备。浏览器的 WebSocket 设不了灵矽握手要求的请求头，所以由服务端中转：浏览器 ⇄ 16k PCM ⇄ `/screen/voice` ⇄ Opus ⇄ 灵矽。

1. 准备一台虚拟设备并绑定到智能体：运行 `uv run --group devsim python tools/devsim.py ota` 拿到 6 位激活码，在智控台「设备管理 → 新增」里填入；绑定后再运行一次，连接信息会保存到 `.data/devsim.json`。
2. 服务端设置 `POZHAN_LINX_DEVICE=.data/devsim.json`（Docker 里把这个文件挂进容器）。服务端需要系统库 libopus（镜像里已装；macOS 上 `brew install opus`）。
3. 必须用 **HTTPS** 打开页面，浏览器才允许使用麦克风。

限制：一台虚拟设备同一时间只服务**一个**网页玩家，第二个人会看到「已经有人在网页上玩了」。开了网页开玩以后，拿到 `POZHAN_SCREEN_TOKEN` 的人就能操作对局，不要公开这个链接。

## 换音色时检验语气

嫌疑人每升一档，回复开头的 emoji 就会变，平台据此切换 TTS 的语气。**但不是每个音色都支持所有情绪**。实测「爽快思思（多情感）」时，😏、😱、😳、🤔 和基线听不出区别，😠、😲、😭、😔、😆 的区别很明显。所以换音色后要重新检验，方法见 `tools/prosody.py` 文件开头的说明：
1. 用同一句台词，分别配上不同的 emoji，录下语音；
2. 用 `tools/prosody.py` 比较音高和能量；
3. 只把真正起作用的情绪写进案件的 `stages`。

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| 设备连上后立刻断开，服务端没有收到任何请求 | 「我的模型」的 API 密钥为空。填上与 `POZHAN_API_KEY` 相同的值 |
| 服务端日志里出现 401 | 「我的模型」的 API 密钥与 `POZHAN_API_KEY` 不一致 |
| 嫌疑人只会重复几句固定台词 | 服务端没有配置 `LLM_BASE_URL` / `LLM_API_KEY`，或者大模型调用失败。查服务日志里的 `suspect generation failed` |
| 回复很慢 | 确认 `LLM_EXTRA_BODY` 关闭了思考（默认已关闭）；用 `evals/latency.py` 比较模型的首字延迟 |
| 不确定平台发来的请求长什么样 | 设置 `POZHAN_LOG_REQUESTS=1`，原始请求会写到 `logs/requests.jsonl`（不含鉴权头） |
| 网页开玩一直「正在连接灵矽…」 | 检查 `POZHAN_LINX_DEVICE` 指向的设备是否已在智控台绑定到本智能体；「我的模型」的 API 密钥不能为空，否则灵矽握手后会立刻断开 |
| 网页开玩按下按钮没反应 | 页面必须是 HTTPS，并在浏览器地址栏里允许使用麦克风 |
| 陪玩屏一直停在开局画面 | 检查链接里的 `token` 是否和 `POZHAN_SCREEN_TOKEN` 一致；指定了 `device` 时，检查设备 MAC 是否写对 |
| 多台设备会串局 | 平台请求里没有设备标识时，所有设备共用一局。设置 `POZHAN_LOG_REQUESTS=1` 后查看请求头，并在 Issue 里反馈 |
