"""知乎公开页正文提取测试 — js-initialData JSON 优先，RichText HTML 兜底。"""

import json

from app.collector.zhihu_page import extract_content_html

_ARTICLE_INITIAL_DATA = {
    "initialState": {
        "entities": {
            "articles": {
                "123": {"id": 123, "title": "文章", "content": "<p>文章全文</p>"},
            }
        }
    }
}

_ANSWER_INITIAL_DATA = {
    "initialState": {
        "entities": {
            "answers": {
                "9": {"id": 9, "content": "<p>回答全文</p>"},
            }
        }
    }
}


def _page(initial_data=None, richtext=None):
    parts = ["<html><head>"]
    if initial_data is not None:
        parts.append(
            '<script id="js-initialData" type="application/json">'
            + json.dumps(initial_data)
            + "</script>"
        )
    parts.append("</head><body>")
    if richtext is not None:
        parts.append(richtext)
    parts.append("</body></html>")
    return "".join(parts)


class TestExtractContentHtml:
    def test_article_from_initial_data(self):
        html = _page(initial_data=_ARTICLE_INITIAL_DATA)
        assert extract_content_html(html) == "<p>文章全文</p>"

    def test_answer_from_initial_data(self):
        html = _page(initial_data=_ANSWER_INITIAL_DATA)
        assert extract_content_html(html) == "<p>回答全文</p>"

    def test_richtext_fallback(self):
        html = _page(
            richtext='<div class="RichText Post-RichTextContainer"><p>正文甲</p><div class="inner">嵌套</div></div>'
        )
        result = extract_content_html(html)
        assert result is not None
        assert "<p>正文甲</p>" in result
        assert "嵌套" in result

    def test_no_content_returns_none(self):
        assert extract_content_html(_page()) is None
        assert extract_content_html("") is None

    def test_broken_initial_data_falls_back_to_richtext(self):
        html = (
            '<html><script id="js-initialData" type="application/json">{broken</script>'
            '<body><div class="RichText"><p>兜底正文</p></div></body></html>'
        )
        result = extract_content_html(html)
        assert result is not None
        assert "<p>兜底正文</p>" in result
