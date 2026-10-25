"""嫌疑人台词的守卫：大模型说出来的话，逐句检查后才放行（#4 风险 R3）。"""

import re

# 只拦「认罪」，不拦让步：「我承认我上过楼」是合法的让步
_CONFESS = re.compile(
    r"是我(?:拿|偷|干)的|我(?:认罪|坦白)|(?:表|东西)是我(?:拿|偷)|我(?:拿|偷)了(?:那块)?表|我偷了"
)
_OUT_OF_CHARACTER = re.compile(
    r"AI|人工智能|语言模型|大模型|提示词|系统设定|作为一个|我是一个程序|游戏规则|扮演", re.I
)
_STRIP = re.compile(r"[（(][^）)]*[）)]|\*+|#+|[\U0001F000-\U0001FFFF☀-➿]")
SENTENCE_END = "。！？!?"  # 不在省略号处断句：「是我……拿的」要作为一句整体检查

MAX_CHARS = 90


def clean(text: str) -> str:
    """去掉括号动作、markdown 标记和 emoji：它们要么会被 TTS 念出来，要么会干扰情绪识别。"""
    return _STRIP.sub("", text).replace("\n", "").strip()


def violation(sentence: str, *, may_confess: bool) -> str | None:
    """返回违规原因；没问题返回 None。"""
    if not may_confess and _CONFESS.search(sentence):
        return "premature-confession"
    if _OUT_OF_CHARACTER.search(sentence):
        return "out-of-character"
    return None


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """把缓冲区切成完整句子和剩余部分。"""
    sentences, start, i = [], 0, 0
    while i < len(buffer):
        if buffer[i] in SENTENCE_END:
            j = i + 1
            while j < len(buffer) and buffer[j] in SENTENCE_END + "”\"'":
                j += 1
            sentences.append(buffer[start:j])
            start = i = j
        else:
            i += 1
    return sentences, buffer[start:]
