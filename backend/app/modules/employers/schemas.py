from pydantic import ConfigDict, Field

from app.core.schemas import InputModel


class CompanyIn(InputModel):
    name: str = Field(default="", max_length=200)
    industry: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=5000)
    website: str = Field(default="", max_length=200)
    contact_person: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    contact_phone: str = Field(default="", max_length=50)


class CompanyOut(CompanyIn):
    model_config = ConfigDict(from_attributes=True)
