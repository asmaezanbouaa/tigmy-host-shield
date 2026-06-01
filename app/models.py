import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_public_id() -> str:
    return str(uuid.uuid4())


class FormLinkStatus(str, enum.Enum):
    ACTIVE = "active"
    SUBMITTED = "submitted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class SubmissionStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    ISSUE = "issue"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


ACTIVE_SUBMISSION_STATUSES = (
    SubmissionStatus.SUBMITTED.value,
    SubmissionStatus.CONFIRMED.value,
    SubmissionStatus.ISSUE.value,
    SubmissionStatus.CANCELLED.value,
)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Apartment(Base):
    __tablename__ = "apartments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str] = mapped_column(Text)
    slug: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submissions: Mapped[list["Submission"]] = relationship(back_populates="apartment")


class FormLink(Base):
    __tablename__ = "form_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    property_address: Mapped[str] = mapped_column(Text, default="")
    guest_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=FormLinkStatus.ACTIVE.value, index=True
    )
    single_use: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submissions: Mapped[list["Submission"]] = relationship(back_populates="form_link")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    form_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("form_links.id"), nullable=True, index=True
    )
    apartment_id: Mapped[int] = mapped_column(
        ForeignKey("apartments.id"), index=True
    )

    last_name: Mapped[str] = mapped_column(String(128))
    first_name: Mapped[str] = mapped_column(String(128))
    nationality: Mapped[str] = mapped_column(String(128))
    date_of_birth: Mapped[str] = mapped_column(String(16))
    country_of_residence: Mapped[str] = mapped_column(String(128))
    number_of_guests: Mapped[int] = mapped_column(Integer, default=1)
    number_of_kids: Mapped[int] = mapped_column(Integer, default=0)
    arrival_date: Mapped[str] = mapped_column(String(16))
    departure_date: Mapped[str] = mapped_column(String(16))
    id_document_type: Mapped[str] = mapped_column(String(64))
    id_document_number: Mapped[str] = mapped_column(String(128))
    id_document_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    id_document_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_verification_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_verification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    accept_internal_rules: Mapped[bool] = mapped_column(Boolean, default=False)
    accept_terms: Mapped[bool] = mapped_column(Boolean, default=False)

    signature_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), default=SubmissionStatus.SUBMITTED.value, index=True
    )
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    form_link: Mapped["FormLink | None"] = relationship(back_populates="submissions")
    apartment: Mapped["Apartment"] = relationship(back_populates="submissions")
    document: Mapped["Document | None"] = relationship(
        back_populates="submission", uselist=False
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=new_public_id
    )
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id"), unique=True, index=True
    )
    pdf_path: Mapped[str] = mapped_column(String(512))
    filename: Mapped[str] = mapped_column(String(255))
    rules_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rules_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    submission: Mapped["Submission"] = relationship(back_populates="document")


class RegistryMeta(Base):
    """Key-value store for cumulative archive counts and purge timestamps."""

    __tablename__ = "registry_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
