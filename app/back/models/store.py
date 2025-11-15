from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, Date, DateTime
from sqlalchemy.orm import relationship
from app.back.core.db import Base
from pydantic import BaseModel


# ==========================
# SQLAlchemy ORM 모델
# ==========================
class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)          # 지점코드
    name = Column(String(100), nullable=False)                      # 지점명
    role = Column(Integer, unique=True)                             # 지점 역할 코드 (2 이상)
    status = Column(String(20), nullable=False, default="OPEN")     # OPEN / PAUSED / CLOSED

    business_no = Column(String(20))                                # 사업자번호
    cs_phone = Column(String(20))                                   # 고객센터번호

    opened_at = Column(Date)
    closed_at = Column(Date)

    install_location = Column(Text)                                 # 설치위치
    address = Column(Text)                                          # 상세주소

    kiosk_admin_pin = Column(String(255))                           # 관리자 PIN/비번 (해시 보관)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)
    kiosks = relationship("Kiosk", back_populates="store")


# ==========================
# Pydantic 모델 (읽기용)
# ==========================
class StoreRead(BaseModel):
    id: int
    code: str
    name: str
    role: int | None = None
    status: str
    business_no: str | None = None
    cs_phone: str | None = None
    opened_at: date | None = None
    closed_at: date | None = None
    install_location: str | None = None
    address: str | None = None
    kiosk_admin_pin: str | None = None

    class Config:
        from_attributes = True


# ==========================
# Pydantic 모델 (생성용)
# ==========================
class StoreCreate(BaseModel):
    code: str
    name: str
    role: int
    status: str = "OPEN"
    business_no: str | None = None
    cs_phone: str | None = None
    opened_at: date | None = None
    closed_at: date | None = None
    install_location: str | None = None
    address: str | None = None
    kiosk_admin_pin: str | None = None
