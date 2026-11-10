from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["user", "rater", "admin"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10)


class ProviderConnectionCreate(BaseModel):
    provider: Literal["openrouter", "openai_compat"]
    base_url: str
    label: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=8)
    monthly_budget_usd: float | None = Field(default=None, ge=0)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    role: Role
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class ProviderConnectionResponse(BaseModel):
    id: str
    provider: Literal["openrouter", "openai_compat"]
    label: str
    last4: str
    status: str
