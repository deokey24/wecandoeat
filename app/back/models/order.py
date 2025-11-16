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


class Order(Base):
    __tablename__ = "orders"

    id = Column(BigInteger, primary_key=True, index=True)

    # 지점/키오스크/상품 ID — 모두 NULL 허용
    store_id = Column(BigInteger, ForeignKey("stores.id"), nullable=True)
    kiosk_id = Column(BigInteger, ForeignKey("kiosks.id"), nullable=True)
    product_id = Column(BigInteger, ForeignKey("products.id"), nullable=True)

    # 상품 정보 스냅샷 — 전부 NULL 허용
    product_name = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=True)
    price = Column(Integer, nullable=True)

    vat_amount = Column(Integer, nullable=True)
    service_amount = Column(Integer, nullable=True)

    # 주문번호 — 없어도 OK
    order_no = Column(String(32), unique=False, index=True, nullable=True)

    # 상태값 — NULL 허용
    status = Column(String(20), nullable=True)

    is_cancel = Column(Boolean, nullable=True)
    cancel_reason = Column(String(100), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # 단말 응답 — 전부 NULL 허용
    service_code = Column(String(2), nullable=True)
    reject_code = Column(String(1), nullable=True)
    response_message = Column(String(128), nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)

    approval_no = Column(String(20), nullable=True)
    issuer_code = Column(String(4), nullable=True)
    acquirer_code = Column(String(4), nullable=True)
    issuer_name = Column(String(50), nullable=True)
    acquirer_name = Column(String(50), nullable=True)
    merchant_no = Column(String(15), nullable=True)
    masked_pan = Column(String(64), nullable=True)

    pay_kind_code = Column(String(2), nullable=True)
    pay_type = Column(String(1), nullable=True)
    terminal_sn = Column(String(8), nullable=True)
    cat_id = Column(String(10), nullable=True)
    transaction_id = Column(String(32), nullable=True)
    balance_amount = Column(Integer, nullable=True)
    easy_pay_type = Column(String(8), nullable=True)

    parent_transaction_id = Column(String(32), nullable=True)

    # 전문 원문
    raw_response = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # 관계 — nullable FK도 문제 없음
    store = relationship("Store", back_populates="orders")
    kiosk = relationship("Kiosk", back_populates="orders")
    product = relationship("Product")
