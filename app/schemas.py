from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.date_validation import (
    parse_iso_date,
    validate_date_of_birth,
    validate_stay_dates,
)


class GuestFormSubmit(BaseModel):
    last_name: str = Field(..., min_length=1, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=128)
    nationality: str = Field(..., min_length=1, max_length=128)
    date_of_birth: str = Field(..., min_length=8, max_length=16)
    country_of_residence: str = Field(..., min_length=1, max_length=128)
    number_of_guests: int = Field(..., ge=1, le=50)
    number_of_kids: int = Field(..., ge=0, le=30)
    arrival_date: str = Field(..., min_length=8, max_length=16)
    departure_date: str = Field(..., min_length=8, max_length=16)
    id_document_type: str = Field(..., min_length=1, max_length=64)
    id_document_number: str = Field(..., min_length=1, max_length=128)
    accept_internal_rules: bool
    accept_terms: bool
    signature_data_url: str = Field(..., min_length=100)

    @field_validator("date_of_birth", "arrival_date", "departure_date")
    @classmethod
    def parse_dates(cls, v: str) -> str:
        parse_iso_date(v)
        return v.strip()[:10]

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v: str) -> str:
        validate_date_of_birth(parse_iso_date(v))
        return v

    @field_validator("accept_internal_rules", "accept_terms", mode="before")
    @classmethod
    def must_be_true(cls, v):
        if v is not True and v != "true" and v != "on" and v != 1:
            raise ValueError("Rules and terms must be accepted")
        return True

    @field_validator("signature_data_url")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        if not v.startswith("data:image/png;base64,"):
            raise ValueError("Invalid signature format")
        if len(v) < 200:
            raise ValueError("Signature is too short")
        return v

    @model_validator(mode="after")
    def check_dates_and_guests(self):
        validate_stay_dates(
            parse_iso_date(self.arrival_date),
            parse_iso_date(self.departure_date),
        )
        if self.number_of_kids > self.number_of_guests:
            raise ValueError("Number of children cannot exceed number of guests")
        return self


class AdminSubmissionEdit(BaseModel):
    last_name: str = Field(..., min_length=1, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=128)
    nationality: str = Field(..., min_length=1, max_length=128)
    date_of_birth: str = Field(..., min_length=8, max_length=16)
    country_of_residence: str = Field(..., min_length=1, max_length=128)
    number_of_guests: int = Field(..., ge=1, le=50)
    number_of_kids: int = Field(..., ge=0, le=30)
    arrival_date: str = Field(..., min_length=8, max_length=16)
    departure_date: str = Field(..., min_length=8, max_length=16)
    id_document_type: str = Field(..., min_length=1, max_length=64)
    id_document_number: str = Field(..., min_length=1, max_length=128)
    admin_notes: str | None = Field(default=None, max_length=5000)

    @field_validator("date_of_birth", "arrival_date", "departure_date")
    @classmethod
    def parse_dates(cls, v: str) -> str:
        parse_iso_date(v)
        return v.strip()[:10]

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v: str) -> str:
        validate_date_of_birth(parse_iso_date(v))
        return v

    @model_validator(mode="after")
    def check_dates_and_guests(self):
        validate_stay_dates(
            parse_iso_date(self.arrival_date),
            parse_iso_date(self.departure_date),
        )
        if self.number_of_kids > self.number_of_guests:
            raise ValueError("Number of children cannot exceed number of guests")
        return self


class AdminLogin(BaseModel):
    username: str
    password: str


class StatusUpdate(BaseModel):
    status: Literal["submitted", "confirmed", "issue", "cancelled", "archived"]
