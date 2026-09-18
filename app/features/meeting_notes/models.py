import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_name: Mapped[str] = mapped_column(String(200))
    meeting_title: Mapped[str] = mapped_column(String(300))
    meeting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transcript_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    summary: Mapped["MeetingSummary | None"] = relationship(
        back_populates="transcript", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_transcripts_created_at", "created_at"),)


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        unique=True,
    )
    executive_summary: Mapped[str] = mapped_column(Text)
    key_decisions: Mapped[list] = mapped_column(JSONB)
    action_items: Mapped[list] = mapped_column(JSONB)
    risks: Mapped[list] = mapped_column(JSONB)
    llm_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transcript: Mapped[Transcript] = relationship(back_populates="summary")
