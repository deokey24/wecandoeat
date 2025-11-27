# app/back/models/kiosk_product.py
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.back.core.db import Base


class KioskProduct(Base):
    """
    특정 키오스크에서 사용하는 '상품 스냅샷'
    - Product(마스터)에서 복사해서 생성
    - 이후 수정은 이 테이블만 건드림
    """
    __tablename__ = "kiosk_products"

    id = Column(BigInteger, primary_key=True, index=True)

    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id"), nullable=False)

    # 어느 마스터 Product에서 복사되었는지(선택)
    base_product_id = Column(BigInteger, ForeignKey("products.id"), nullable=True)

    # 실제 키오스크에서 사용하는 값들
    name = Column(String(200), nullable=False)
    code = Column(String(50))
    category = Column(String(50))
    price = Column(Integer, nullable=False)
    is_adult_only = Column(Boolean, nullable=False, default=False)

    image_url = Column(Text)
    detail_url = Column(Text)
    description = Column(Text)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ───────────────── 관계 ─────────────────

    # 이 스냅샷이 속한 키오스크
    kiosk = relationship("Kiosk", back_populates="kiosk_products")

    # 어떤 마스터 Product에서 복사되었는지
    # ↔ Product.kiosk_products 와 양방향 매핑 (Product 쪽도 맞춰줘야 함)
    base_product = relationship("Product", back_populates="kiosk_products")

    # 이 스냅샷을 쓰는 슬롯들
    slot_products = relationship(
        "VendingSlotProduct",
        back_populates="kiosk_product",
        cascade="all, delete-orphan",
    )
