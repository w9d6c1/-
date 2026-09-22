"""渠道身份映射 — 将外部渠道用户映射为系统 (user_id/role/scope)

本期策略:
- 内部渠道(企微/钉钉): 映射为配置的默认内部角色(默认 operator → public+internal)
- 外部渠道(小程序/官网): 匿名 customer 身份

如需按 userid 细分部门/角色,可在 sys_user 建立渠道账号映射后扩展 resolve_internal_identity。
"""

from dataclasses import dataclass

from app.agents.nodes.auth import _DEFAULT_ROLE_SCOPE_MAP, _SCOPE_CACHE


@dataclass
class ChannelIdentity:
    user_id: int | None
    role: str
    department: str | None
    scopes: list[str]
    external_id: str


def _scopes_for_role(role: str) -> list[str]:
    scopes = _SCOPE_CACHE.get(role) or _DEFAULT_ROLE_SCOPE_MAP.get(role)
    if not scopes:
        scopes = ["public"]
    return list(scopes)


def resolve_internal_identity(
    external_id: str,
    default_role: str = "operator",
    department: str | None = None,
) -> ChannelIdentity:
    """内部渠道身份映射(企微/钉钉)。

    external_id: 渠道用户唯一标识(如企微 userid)
    default_role: 未建立映射时使用的默认角色
    """
    role = default_role or "operator"
    scopes = _scopes_for_role(role)
    return ChannelIdentity(
        user_id=None,
        role=role,
        department=department,
        scopes=scopes,
        external_id=external_id,
    )


def resolve_customer_identity(external_id: str) -> ChannelIdentity:
    """外部渠道身份映射(小程序/官网),匿名 customer。"""
    return ChannelIdentity(
        user_id=None,
        role="readonly",
        department=None,
        scopes=["public", "customer"],
        external_id=external_id,
    )
