"""输出节点图片标记校验测试 — 仅保留注册表中真实存在的 [图N]"""

from app.agents.nodes.output import strip_invalid_image_markers


class TestStripInvalidImageMarkers:
    def test_keeps_valid_markers(self):
        text = "原理如图[图1]所示，效果见[图2]。"
        assert strip_invalid_image_markers(text, {1, 2}) == text

    def test_strips_invalid_markers(self):
        text = "原理如图[图1]所示，效果见[图9]。"
        assert strip_invalid_image_markers(text, {1}) == "原理如图[图1]所示，效果见。"
        assert "[图9]" not in strip_invalid_image_markers(text, {1})

    def test_strips_all_when_none_valid(self):
        text = "见[图1]与[图2]。"
        assert "[图" not in strip_invalid_image_markers(text, set())

    def test_collapses_blank_lines_from_removed_marker_lines(self):
        text = "结论如下。\n\n[图1]\n\n第二段。"
        result = strip_invalid_image_markers(text, set())
        assert "[图1]" not in result
        assert "\n\n\n" not in result

    def test_no_markers_returns_unchanged(self):
        text = "没有图片标记的答案。"
        assert strip_invalid_image_markers(text, set()) == text
