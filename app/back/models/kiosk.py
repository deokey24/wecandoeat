# app/back/models/kiosk.py
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Integer,
    Index
)
from sqlalchemy.dialects.postgresql import INET, JSONB
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
    
    kiosk_password = Column(String(100), nullable=False)

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
    screen_images = relationship(
    "KioskScreenImage",
    back_populates="kiosk",
    cascade="all, delete-orphan",
    order_by="KioskScreenImage.sort_order",
    )
    orders = relationship(
        "Order",
        back_populates="kiosk",
        cascade="all, delete-orphan",
    )
    pair_code_4 = Column(String(4), unique=True, nullable=True)
    config_version = Column(Integer, nullable=False, default=1)
    # 🔹 키오스크 전용 상품 스냅샷들
    kiosk_products = relationship(
        "KioskProduct",
        back_populates="kiosk",
        cascade="all, delete-orphan",
    )
    status_logs = relationship(
        "KioskStatusLog", back_populates="kiosk", cascade="all, delete-orphan"
    )
    event_logs = relationship(          # ⬅ 추가
        "KioskEventLog", back_populates="kiosk", cascade="all, delete-orphan"
    )



class KioskStatusLog(Base):
    __tablename__ = "kiosk_status_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id"), nullable=False)

    status = Column(String(20), nullable=False)
    payload = Column(JSONB)  # JSON 문자열로 저장 (JSONB 써도 됨)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    kiosk = relationship("Kiosk", back_populates="status_logs")

class KioskEventLog(Base):
    __tablename__ = "kiosk_event_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id", ondelete="CASCADE"), nullable=False)

    # 상단 공통
    event_type = Column(String(50), nullable=False)   # "PAYMENT"
    event_name = Column(String(100), nullable=False)  # PAY_START / PAY_VEND_OK / PAY_VEND_FAIL
    level = Column(String(20), nullable=False)        # INFO / WARN / ERROR
    message = Column(String, nullable=True)

    # 슬롯 관련
    label_slot = Column(Integer, nullable=True)       # 1~80
    slot_label = Column(String(20), nullable=True)    # "A03" 등

    # 금액 관련
    price_won = Column(Integer, nullable=True)
    paid_won = Column(Integer, nullable=True)

    # 실패 사유
    reason = Column(String(100), nullable=True)       # "SHIP_FAIL" 등

    # 디바이스/앱 정보
    device_uuid = Column(String(255), nullable=True)
    app_version = Column(String(50), nullable=True)

    # 시간
    occurred_at = Column(DateTime(timezone=True), nullable=False)  # 단말 기준
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)  # 서버 기준

    kiosk = relationship("Kiosk", back_populates="event_logs")

    __table_args__ = (
        Index("idx_kiosk_event_logs_kiosk_id_created_at", "kiosk_id", "created_at"),
        Index("idx_kiosk_event_logs_type_name", "event_type", "event_name"),
        Index("idx_kiosk_event_logs_reason", "reason"),
    )

# ★ 새로 추가
class KioskScreenImage(Base):
    __tablename__ = "kiosk_screen_images"

    id = Column(BigInteger, primary_key=True, index=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id", ondelete="CASCADE"), nullable=False)

    # R2에 업로드된 보호화면 이미지 URL
    image_url = Column(String(500), nullable=False)

    # 표시 순서 (작은 숫자일수록 먼저)
    sort_order = Column(Integer, nullable=False, default=0)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    kiosk = relationship("Kiosk", back_populates="screen_images")