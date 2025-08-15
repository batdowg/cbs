from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
    event,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship, validates, object_session

Base = declarative_base()


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkshopType(Base, TimestampMixin):
    __tablename__ = "workshop_type"

    id = Column(Integer, primary_key=True)
    short_name = Column(String, nullable=False, unique=True)
    full_name = Column(String, nullable=False, unique=True)
    active = Column(Boolean, nullable=False, server_default=func.true())

    sessions = relationship("Session", back_populates="workshop_type")

    def __repr__(self) -> str:
        return f"<WorkshopType id={self.id} short_name={self.short_name!r}>"


class Company(Base, TimestampMixin):
    __tablename__ = "company"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    normalized_name = Column(String, nullable=False)
    active = Column(Boolean, nullable=False, server_default=func.true())

    sessions = relationship("Session", back_populates="company")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


class Session(Base, TimestampMixin):
    __tablename__ = "session"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("company.id"), nullable=False)
    workshop_type_id = Column(Integer, ForeignKey("workshop_type.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    client_manager_name = Column(String)
    client_manager_email = Column(String)
    created_by_user_id = Column(Integer, ForeignKey("user_account.user_account_id"))
    shipping_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    notes = Column(Text)

    __table_args__ = (
        Index("ux_session_session_id", "session_id", unique=True),
        Index("ix_session_client_manager_email_lower", func.lower(client_manager_email)),
    )

    company = relationship("Company", back_populates="sessions")
    workshop_type = relationship("WorkshopType", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<Session id={self.id} session_id={self.session_id!r}>"

    @validates("client_manager_email")
    def _validate_email(self, key: str, value: Optional[str]) -> Optional[str]:
        value = (value or "").lower()
        sess = object_session(self)
        if sess is not None:
            q = sess.query(Session).filter(func.lower(Session.client_manager_email) == value)
            if self.id is not None:
                q = q.filter(Session.id != self.id)
            if q.first() is not None:
                raise ValueError("client_manager_email must be unique")
        return value


@event.listens_for(Session, "before_insert")
def generate_session_id(mapper, connection, target: Session) -> None:
    company_name = connection.execute(
        select(Company.normalized_name).where(Company.id == target.company_id)
    ).scalar() or ""
    short = connection.execute(
        select(WorkshopType.short_name).where(WorkshopType.id == target.workshop_type_id)
    ).scalar() or ""
    prefix = company_name.strip().upper()[:5]
    prefix = prefix.ljust(5, "X")
    date_part = target.end_date.strftime("%Y%m%d") if isinstance(target.end_date, date) else ""
    target.session_id = f"{prefix}-{short}-{date_part}"
