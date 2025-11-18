# app/back/models/qr_auth.py
from datetime import datetime, timezone
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.back.core.db import Base     # 또는 from ..core.db import Base


class QrAuthStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class QrAuthSession(Base):
    __tablename__ = "qr_auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    kiosk_id = Column(Integer, ForeignKey("kiosks.id"), nullable=False, index=True)

    status = Column(
        Enum(QrAuthStatus, native_enum=False),
        nullable=False,
        default=QrAuthStatus.PENDING,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 🔽 SMS 인증 관련 필드
    phone_number = Column(String(20), nullable=True)
    sms_code = Column(String(10), nullable=True)
    sms_sent_at = Column(DateTime(timezone=True), nullable=True)

    kiosk = relationship("Kiosk", backref="qr_auth_sessions")