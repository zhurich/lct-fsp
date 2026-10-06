from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.models import Role


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    consent: bool = Field(description="Согласие на обработку персональных данных")

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Без согласия на обработку персональных данных регистрация невозможна")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenIn(BaseModel):
    token: str


class EmailIn(BaseModel):
    email: EmailStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
    consent_at: datetime = Field(description="Когда дано согласие на обработку персональных данных")


class RegisteredOut(BaseModel):
    message: str
    verified: bool = Field(description="true — почта уже подтверждена (демо-режим), можно входить")


class Message(BaseModel):
    message: str
