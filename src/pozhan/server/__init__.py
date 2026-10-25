"""灵矽接入层：把游戏伪装成一个 OpenAI 兼容的大模型，供灵矽「我的模型」调用。"""

from pozhan.server.app import create_app

__all__ = ["create_app"]
