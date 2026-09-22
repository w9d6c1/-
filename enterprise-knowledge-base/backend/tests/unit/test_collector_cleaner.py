"""采集层 HTML 清洗器测试"""

from app.collector.cleaner import clean_html, clean_html_with_images, extract_title, strip_image_placeholders


class TestCleanHtml:
    def test_strips_script_and_style(self):
        html = "<p>正文</p><script>var x=1;</script><style>.a{color:red}</style><p>结尾</p>"
        result = clean_html(html)
        assert "正文" in result
        assert "结尾" in result
        assert "var x" not in result
        assert "color:red" not in result

    def test_strips_nav_header_footer(self):
        html = "<nav>导航</nav><header>头部</header><article>核心内容</article><footer>页脚</footer>"
        result = clean_html(html)
        assert "核心内容" in result
        assert "导航" not in result
        assert "头部" not in result
        assert "页脚" not in result

    def test_block_tags_produce_newlines(self):
        html = "<h1>标题</h1><p>段落一</p><p>段落二</p>"
        result = clean_html(html)
        assert "标题\n段落一\n段落二" == result

    def test_collapses_whitespace_and_nbsp(self):
        html = "<p>多&nbsp;&nbsp;空白&emsp;内容</p>"
        result = clean_html(html)
        assert result == "多 空白 内容"

    def test_unescapes_entities(self):
        html = "<p>A &amp; B &lt;C&gt;</p>"
        assert clean_html(html) == "A & B <C>"

    def test_empty_input(self):
        assert clean_html("") == ""
        assert clean_html("   ") == ""

    def test_malformed_html_fallback(self):
        html = "<p>未闭合<div>嵌套<span>文本"
        result = clean_html(html)
        assert "未闭合" in result
        assert "文本" in result
        assert "<" not in result

    def test_list_items_separated(self):
        html = "<ul><li>项目一</li><li>项目二</li></ul>"
        result = clean_html(html)
        assert "项目一" in result
        assert "项目二" in result
        assert result.split("\n") == ["项目一", "项目二"]


class TestExtractTitle:
    def test_extracts_title_tag(self):
        html = "<html><head><title>  文章标题  </title></head><body><p>正文</p></body></html>"
        assert extract_title(html) == "文章标题"

    def test_no_title_returns_empty(self):
        assert extract_title("<p>无标题</p>") == ""

    def test_empty_input(self):
        assert extract_title("") == ""

    def test_title_not_in_body_text(self):
        html = "<head><title>标题</title></head><body>正文</body>"
        assert extract_title(html) == "标题"
        assert "标题" not in clean_html(html)


class TestCleanHtmlWithImages:
    def test_inserts_placeholders_in_order(self):
        html = (
            '<p>第一段</p>'
            '<img data-src="https://a.com/1.jpg">'
            '<p>第二段</p>'
            '<img data-src="https://b.com/2.jpg">'
        )
        text, count = clean_html_with_images(html)
        assert count == 2
        assert "[[IMG:1]]" in text
        assert "[[IMG:2]]" in text
        # 占位符编号顺序与 parse_images 一致
        assert text.index("[[IMG:1]]") < text.index("[[IMG:2]]")

    def test_ignores_imgs_without_resolvable_src(self):
        html = '<p>x</p><img><img src="data:image/gif;base64,aaa"><img data-src="https://c.com/3.jpg">'
        text, count = clean_html_with_images(html)
        assert count == 1
        assert "[[IMG:1]]" in text
        assert "[[IMG:2]]" not in text

    def test_skips_images_in_script(self):
        html = '<script>var imgs="<img src=https://x.com/1.jpg>"</script><p>正文</p>'
        text, count = clean_html_with_images(html)
        assert count == 0
        assert "[[IMG:" not in text

    def test_empty_input(self):
        assert clean_html_with_images("") == ("", 0)


class TestStripImagePlaceholders:
    def test_strips_placeholders_and_matches_clean_html(self):
        html = '<p>第一段</p><img data-src="https://a.com/1.jpg"><p>第二段</p>'
        text, count = clean_html_with_images(html)
        assert count == 1
        stripped = strip_image_placeholders(text)
        assert "[[IMG:" not in stripped
        assert stripped == clean_html(html)

    def test_no_placeholders_returns_as_is(self):
        assert strip_image_placeholders("普通文本") == "普通文本"

