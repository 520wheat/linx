"""嫌疑人台词的守卫：大模型说出来的话，逐句检查后才放行（#4 风险 R3）。"""

import re

# 只拦「认罪」，不拦让步：「我承认我上过楼」是合法的让步
_CONFESS = re.compile(
    r"是我(?:拿|偷|干)的|我(?:认罪|坦白)|(?:表|东西)是我(?:拿|偷)|我(?:拿|偷)了(?:那块)?表|我偷了"
)
_OUT_OF_CHARACTER = re.compile(
    r"AI|人工智能|语言模型|大模型|提示词|系统设定|作为一个|我是一个程序|游戏规则|扮演", re.I
)
# 大模型会模仿上下文里的旁白腔（「证词四被戳破了」「他只能让步」），甚至把任务说明念出来（#46 自对弈发现）
_NARRATOR_VOICE = re.compile(
    r"被戳破|他只能让步|他改口了|他还在坚持|律师还有|这是证词|证词[一二三四五六七八九十\d]"
)
_STRIP = re.compile(r"[（(][^）)]*[）)]|\*+|#+|[\U0001F000-\U0001FFFF☀-➿]")
SENTENCE_END = "。！？!?"
# 流式输出时在逗号处也先放出一段，尽早开始 TTS（#22）；守卫按已说出的全部内容、去掉标点后检查
CLAUSE_END = SENTENCE_END + "，,；;"
_PUNCT = re.compile(r"[\s，,。.！!？?；;：:、…—\-~“”\"'‘’]")

MAX_CHARS = 90


def clean(text: str) -> str:
    """去掉括号动作、markdown 标记和 emoji：它们要么会被 TTS 念出来，要么会干扰情绪识别。"""
    return _STRIP.sub("", text).replace("\n", "").strip()


def violation(sentence: str, *, may_confess: bool) -> str | None:
    """返回违规原因；没问题返回 None。去掉标点再匹配：「是我，拿的」也算认罪。"""
    plain = _PUNCT.sub("", sentence)
    if not may_confess and _CONFESS.search(plain):
        return "premature-confession"
    if _OUT_OF_CHARACTER.search(plain):
        return "out-of-character"
    if _NARRATOR_VOICE.search(plain):
        return "narrator-voice"
    return None


def split_sentences(buffer: str, ends: str = SENTENCE_END) -> tuple[list[str], str]:
    """把缓冲区切成完整的句子（或分句）和剩余部分。"""
    sentences, start, i = [], 0, 0
    while i < len(buffer):
        if buffer[i] in ends:
            j = i + 1
            while j < len(buffer) and buffer[j] in ends + "”\"'":
                j += 1
            sentences.append(buffer[start:j])
            start = i = j
        else:
            i += 1
    return sentences, buffer[start:]
