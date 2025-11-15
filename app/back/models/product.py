# app/back/models/product.py
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.back.core.db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    category = Column(String(50))
    price = Column(Integer, nullable=False)
    is_adult_only = Column(Boolean, default=False, nullable=False)

    # R2 오브젝트 키 (원본 key)
    image_object_key = Column(Text)      # 예: "products/images/abcd1234.jpg"
    detail_object_key = Column(Text)     # 예: "products/details/efgh5678.jpg"

    # 화면에서 쓸 실제 URL (지금 당장 사용)
    image_url = Column(Text)
    detail_url = Column(Text)

    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    vending_slots = relationship("VendingSlotProduct", back_populates="product")


# ================= Pydantic =================

class ProductRead(BaseModel):
    id: int
    name: str
    code: str | None = None
    category: str | None = None
    price: int
    is_adult_only: bool

    image_object_key: str | None = None
    detail_object_key: str | None = None

    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime
    # 필요하면 updated_at도 나중에 추가 가능
    # updated_at: datetime

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    price: int
    code: str | None = None
    category: str | None = None
    is_adult_only: bool = False

    image_object_key: str | None = None
    detail_object_key: str | None = None

    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None


class ProductUpdate(BaseModel):
    name: str
    price: int
    code: str | None = None
    category: str | None = None
    is_adult_only: bool = False

    image_object_key: str | None = None
    detail_object_key: str | None = None

    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None
    is_active: bool = True
