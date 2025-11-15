# app/back/models/product.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.back.core.db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)          # 상품명
    code = Column(String(50))                           # 내부코드/바코드
    category = Column(String(50))                       # 카테고리
    price = Column(Integer, nullable=False)             # 판매가
    is_adult_only = Column(Boolean, default=False, nullable=False)  # 성인상품 여부

    image_url = Column(Text)                            # 이미지 URL
    detail_url = Column(Text)                           # 상세설명 URL
    description = Column(Text)                          # 짧은 설명

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
    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProductCreate(BaseModel):
    name: str
    price: int
    code: str | None = None
    category: str | None = None
    is_adult_only: bool = False
    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None


class ProductUpdate(BaseModel):
    name: str
    price: int
    code: str | None = None
    category: str | None = None
    is_adult_only: bool = False
    image_url: str | None = None
    detail_url: str | None = None
    description: str | None = None
    is_active: bool = True
