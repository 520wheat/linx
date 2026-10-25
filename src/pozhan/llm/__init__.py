"""OpenAI 兼容的大模型客户端。intent 和 director 是仅有的两个调用方。"""

from pozhan.llm.client import LLM, LLMError, Message, OpenAICompatLLM

__all__ = ["LLM", "LLMError", "Message", "OpenAICompatLLM"]
