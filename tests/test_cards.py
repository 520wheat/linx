from pozhan.cards import render


def test_cards_render_every_card_and_the_help_card(case):
    html = render(case)
    for card in case.cards:
        assert card.title in html and card.text in html
    assert "玩法速查" not in html  # 用了字间距写法
    assert "玩 法 速 查" in html and "用 X 号卡反驳证词 Y" in html
    assert html.count('class="page"') == 2  # 4 张线索卡 + 1 张速查卡 → 两页


def test_cards_escape_html(case):
    from dataclasses import replace

    from pozhan.case.model import Card

    evil = replace(case, cards=(Card(1, "<b>x</b>", "a & b"),))
    html = render(evil)
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "a &amp; b" in html


def test_card_art_is_embedded_when_it_exists(case, tmp_path, monkeypatch):
    # 线索卡插图（#63）：有图就内嵌成 data URI，没有图保持纯文字
    import pozhan.cards as cards

    (tmp_path / case.id).mkdir()
    (tmp_path / case.id / "card-2.jpg").write_bytes(b"\xff\xd8fake-jpeg")
    monkeypatch.setattr(cards, "ART", tmp_path)
    html = cards.render(case)
    assert html.count("data:image/jpeg;base64,") == 1
    assert html.count('class="card has-art"') == 1
