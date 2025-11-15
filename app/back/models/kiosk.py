# app/back/models/kiosk.py
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import relationship

from app.back.core.db import Base


class Kiosk(Base):
    __tablename__ = "kiosks"

    id = Column(BigInteger, primary_key=True, index=True)
    store_id = Column(BigInteger, ForeignKey("stores.id"), nullable=False)

    # 물리 기기/위치 정보
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    location_hint = Column(String(200))
    serial_no = Column(String(100))
    status = Column(String(20), nullable=False, default="ACTIVE")

    # 앱/통신 관련
    api_key = Column(String(255))
    device_uuid = Column(String(100))
    is_active = Column(Boolean, nullable=False, default=True)
    last_heartbeat_at = Column(DateTime(timezone=True))
    last_ip = Column(INET)
    app_version = Column(String(50))

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    store = relationship("Store", back_populates="kiosks")
    slots = relationship("VendingSlot", back_populates="kiosk", cascade="all, delete-orphan")
    status_logs = relationship(
        "KioskStatusLog", back_populates="kiosk", cascade="all, delete-orphan"
    )



class KioskStatusLog(Base):
    __tablename__ = "kiosk_status_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id"), nullable=False)

    status = Column(String(20), nullable=False)
    payload = Column(String)  # JSON 문자열로 저장 (JSONB 써도 됨)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    kiosk = relationship("Kiosk", back_populates="status_logs")
