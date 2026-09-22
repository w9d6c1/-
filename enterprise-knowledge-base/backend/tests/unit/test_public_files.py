"""单元测试 — 公开文件代理的前缀/扩展名白名单与路径安全"""

import pytest
from fastapi import HTTPException

from app.api.public_files import _validate_object_name


class TestValidateObjectName:
    def test_allow_article_images_prefix(self):
        assert (
            _validate_object_name("article-images/wechat/a/photo.jpg")
            == "article-images/wechat/a/photo.jpg"
        )

    def test_allow_article_photos_prefix(self):
        assert (
            _validate_object_name("article-photos/12/photo.png")
            == "article-photos/12/photo.png"
        )

    def test_reject_other_prefix(self):
        with pytest.raises(HTTPException) as exc:
            _validate_object_name("other-prefix/a.jpg")
        assert exc.value.status_code == 403

    def test_reject_disallowed_extension(self):
        with pytest.raises(HTTPException) as exc:
            _validate_object_name("article-photos/12/evil.txt")
        assert exc.value.status_code == 403

    def test_reject_path_traversal(self):
        with pytest.raises(HTTPException):
            _validate_object_name("../article-photos/12/secret.jpg")
