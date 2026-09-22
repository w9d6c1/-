"""用户 Pydantic 请求/响应 Schema"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

VALID_ROLES = ("superadmin", "dept_admin", "operator", "readonly")


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str
    display_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=20)
    role: Literal["superadmin", "dept_admin", "operator", "readonly"] = "readonly"
    department: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def passwords_match(self) -> "UserCreate":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self


class UserResponse(BaseModel):
    id: int
    username: str | None = None
    phone: str | None = None
    display_name: str | None = None
    email: str | None = None
    role: str
    department: str | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    role: Literal["superadmin", "dept_admin", "operator", "readonly"] | None = None
    department: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class SendCodeRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)


class PhoneLoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=6, max_length=6)


class PhonePasswordLoginRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    password: str = Field(min_length=1)


class ResetPasswordRequest(BaseModel):
    phone: str = Field(min_length=11, max_length=20)
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)
    password_confirm: str

    @model_validator(mode="after")
    def passwords_match(self) -> "ResetPasswordRequest":
        if self.new_password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self
