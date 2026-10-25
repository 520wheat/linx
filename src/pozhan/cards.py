"""线索卡打印：根据案件生成 A4 可打印的 HTML，一页四张卡，外加一张玩法速查卡（#12）。

线索卡是实体卡（Proposal #3 决策 4），开局摆在桌上，玩家「拍卡」出示。
"""

from html import escape

from pozhan.case.model import Case

CSS = """
@page { size: A4; margin: 10mm; }
* { box-sizing: border-box; }
body { margin: 0; color: #1c1917;
       font-family: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif; }
.page { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 6mm;
        height: 277mm; page-break-after: always; }
.page:last-child { page-break-after: auto; }
.card { border: 1.2mm solid #1c1917; border-radius: 5mm; padding: 9mm 8mm;
        display: flex; flex-direction: column; position: relative; overflow: hidden; }
.card .tag { font-size: 11pt; letter-spacing: 0.3em; color: #78716c; }
.card .no { font-size: 64pt; font-weight: 800; line-height: 1; margin: 4mm 0 2mm; }
.card .no small { font-size: 22pt; font-weight: 600; margin-left: 2mm; }
.card h2 { font-size: 20pt; margin: 2mm 0 5mm; }
.card p { font-size: 15pt; line-height: 1.7; margin: 0; }
.card .case { position: absolute; bottom: 6mm; right: 8mm; font-size: 9pt; color: #a8a29e; }
.help h2 { font-size: 18pt; }
.help ol { font-size: 12.5pt; line-height: 1.75; padding-left: 6mm; margin: 0; }
.help b { font-weight: 700; }
@media screen { body { background: #e7e5e4; padding: 8mm; } .page { background: #fff; padding: 6mm;
  max-width: 210mm; margin: 0 auto 8mm; height: auto; min-height: 277mm; } }
"""


def _card(case: Case, card_id: int, title: str, text: str) -> str:
    return (
        '<div class="card">'
        '<div class="tag">线 索 卡</div>'
        f'<div class="no">{card_id}<small>号卡</small></div>'
        f"<h2>{escape(title)}</h2><p>{escape(text)}</p>"
        f'<div class="case">《破绽》· {escape(case.title)}</div>'
        "</div>"
    )


def _help(case: Case) -> str:
    return (
        '<div class="card help">'
        '<div class="tag">玩 法 速 查</div>'
        f"<h2>审问 {escape(case.suspect.name)}</h2>"
        "<ol>"
        "<li>对设备说<b>「开始审讯」</b>，听案情和三条证词。</li>"
        "<li>随便提问，找出证词里的破绽。</li>"
        "<li>拍出一张卡，说<b>「用 X 号卡反驳证词 Y」</b>。</li>"
        f"<li>戳穿全部证词就破案；出示错 {case.limits.strikes} 次或超过 "
        f"{case.limits.minutes} 分钟，律师就到了。</li>"
        "<li>随时可以说：<b>念一下证词</b> · <b>念一下 X 号卡</b> · <b>还有几次机会</b> · "
        "<b>再说一遍</b> · <b>重新开始</b>。</li>"
        "</ol>"
        f'<div class="case">《破绽》· {escape(case.title)}</div>'
        "</div>"
    )


def render(case: Case) -> str:
    cards = [_card(case, c.id, c.title, c.text) for c in case.cards] + [_help(case)]
    pages = ["".join(cards[i : i + 4]) for i in range(0, len(cards), 4)]
    body = "".join(f'<section class="page">{p}</section>' for p in pages)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f"<title>《破绽》线索卡 · {escape(case.title)}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )
