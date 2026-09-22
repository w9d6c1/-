"""渠道身份映射测试"""

from app.services.identity_service import (
    resolve_customer_identity,
    resolve_internal_identity,
)


class TestInternalIdentity:
    def test_default_operator_scopes(self):
        identity = resolve_internal_identity("user001", default_role="operator")
        assert identity.external_id == "user001"
        assert identity.role == "operator"
        assert "public" in identity.scopes
        assert "internal" in identity.scopes
        assert "customer" not in identity.scopes

    def test_readonly_role_only_public(self):
        identity = resolve_internal_identity("user002", default_role="readonly")
        assert identity.scopes == ["public"]

    def test_unknown_role_falls_back_public(self):
        identity = resolve_internal_identity("user003", default_role="ghost_role")
        assert identity.scopes == ["public"]


class TestCustomerIdentity:
    def test_customer_scopes(self):
        identity = resolve_customer_identity("openid_abc")
        assert identity.external_id == "openid_abc"
        assert identity.scopes == ["public", "customer"]
        assert "internal" not in identity.scopes
