"""网页开玩（#43）：网页充当一台灵矽设备，语音全程走灵矽。

浏览器的 WebSocket 设不了灵矽要求的握手请求头，Opus 编解码也不便放在浏览器里，
所以由服务端中转：浏览器 ⇄ PCM ⇄ 本服务 ⇄ Opus ⇄ 灵矽。
"""

from pozhan.voice.relay import LinxDevice, VoiceRelay

__all__ = ["LinxDevice", "VoiceRelay"]
