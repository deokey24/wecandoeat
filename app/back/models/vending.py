# app/back/models/vending.py
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.orm import relationship

from app.back.core.db import Base


class VendingSlot(Base):
    __tablename__ = "vending_slots"

    id = Column(BigInteger, primary_key=True, index=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id"), nullable=False)

    row = Column(SmallInteger, nullable=False)
    col = Column(SmallInteger, nullable=False)
    board_code = Column(String(10), nullable=False)
    label = Column(String(20))
    max_capacity = Column(SmallInteger, nullable=False, default=0)
    is_enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    kiosk = relationship("Kiosk", back_populates="slots")
    slot_product = relationship(
        "VendingSlotProduct",
        back_populates="slot",
        uselist=False,
        cascade="all, delete-orphan",
    )


class VendingSlotProduct(Base):
    __tablename__ = "vending_slot_products"

    id = Column(BigInteger, primary_key=True, index=True)
    slot_id = Column(BigInteger, ForeignKey("vending_slots.id"), nullable=False)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=False)

    current_stock = Column(Integer, nullable=False, default=0)
    low_stock_alarm = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    slot = relationship("VendingSlot", back_populates="slot_product")
    product = relationship("Product", back_populates="vending_slots")
