"""图片提取器测试 — src 解析、占位符一致性、对象名构建"""

from app.collector.image_extractor import (
    build_object_name,
    image_url_path,
    parse_images,
    resolve_img_src,
)


class TestResolveImgSrc:
    def test_wechat_data_src_priority(self):
        attrs = [("data-src", "https://mmbiz.qpic.cn/a.jpg"), ("src", "data:image/gif;base64,xxx")]
        assert resolve_img_src(attrs) == "https://mmbiz.qpic.cn/a.jpg"

    def test_zhihu_data_actualsrc(self):
        attrs = [("data-actualsrc", "https://picx.zhimg.com/50/x.jpg"), ("src", "https://picx.zhimg.com/200x200/x.jpg")]
        assert resolve_img_src(attrs) == "https://picx.zhimg.com/50/x.jpg"

    def test_data_uri_skipped(self):
        attrs = [("src", "data:image/png;base64,iVBORw0KGgo=")]
        assert resolve_img_src(attrs) is None

    def test_empty_or_missing(self):
        assert resolve_img_src([]) is None
        assert resolve_img_src([("alt", "no src")]) is None


class TestParseImages:
    def test_parses_in_order(self):
        html = (
            "<p>正文</p>"
            '<img src="https://a.com/1.jpg">'
            '<img data-src="https://b.com/2.jpg">'
            '<img src="data:image/png;base64,xxx">'
            '<img src="https://c.com/3.png">'
        )
        images = parse_images(html)
        urls = [img.url for img in images]
        assert urls == ["https://a.com/1.jpg", "https://b.com/2.jpg", "https://c.com/3.png"]

    def test_skips_tiny_placeholder_imgs_without_src(self):
        html = '<img src=""><img><img src="data:image/gif;base64,aaa">'
        assert parse_images(html) == []

    def test_captures_width_height(self):
        html = '<img data-src="https://a.com/x.jpg" data-w="600" height="400">'
        images = parse_images(html)
        assert len(images) == 1
        assert images[0].width == 600
        assert images[0].height == 400

    def test_empty_input(self):
        assert parse_images("") == []
        assert parse_images("<p>无图</p>") == []


class TestBuildObjectName:
    def test_object_name_shape(self):
        name = build_object_name("wechat", "wx_001", "abc123", "jpg")
        assert name == "article-images/wechat/wx_001/abc123.jpg"

    def test_sanitizes_external_id(self):
        name = build_object_name("zhihu", "https://www.zhihu.com/question/1", "h", "png")
        # 结构：article-images/{platform}/{safe_id}/{hash}.{ext}，safe_id 内无 / 或 ..
        inner = name.replace("article-images/zhihu/", "").split("/")
        assert inner[0] == "https_www_zhihu_com_question_1"
        assert inner[1] == "h.png"
        assert ".." not in name

    def test_image_url_path(self):
        assert image_url_path("article-images/wechat/a/b.jpg") == "/api/public/images/article-images/wechat/a/b.jpg"
