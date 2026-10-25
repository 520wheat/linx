# 午夜便利店 · 审讯 Demo

七牛云黑客松作品：**用线索卡拆穿嫌疑人的不在场证明**。

当前版本是可玩前端 Demo：点最多两张线索卡出示证据，再按住问话。浏览器语音（Web Speech）负责听你说话、让嫌疑人开口。灵矽实时语音接口预留在 `js/linx.js`，有 Token 后可替换。

## 怎么玩

1. 本地打开（推荐）：

```bash
cd linx
python -m http.server 8080
```

浏览器访问 http://localhost:8080

2. 点「开始审讯」。
3. 查看线索板，最多点亮两张卡。
4. 按住「问话」，说出你的质问。
5. 把「便利店小票」和「小区监控」一起出示并追问时间，即可拆穿不在场证明。

审讯限时 8 分钟。Chrome / Edge 语音识别更稳，需允许麦克风。

## 仓库结构

- `index.html` 入口与界面
- `css/app.css` 审讯室 HUD
- `js/case.js` 唯一案件与关键组合
- `js/voice.js` 浏览器语音（可替换为灵矽）
- `js/game.js` 玩法状态
- `js/linx.js` 灵矽 WebSocket 接入占位

## 灵矽接入

把 `LINX_TOKEN`、`DEVICE_ID` 填进 `js/linx.js` 后，将 `voice.js` 的 `speakSuspect` / `listenPlayer` 切到 WebSocket 音频流即可。没有密钥时 Demo 仍可完整演示玩法。
