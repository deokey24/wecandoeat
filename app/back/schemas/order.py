# app/back/schemas/order.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OrderCreate(BaseModel):
    # 어떤 키오스크에서 날아온 건지 식별 (필수)
    kiosk_code: str

    # 상품/매출 정보 (전부 옵션)
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    quantity: Optional[int] = 1
    price: Optional[int] = None          # 총 결제 금액
    vat_amount: Optional[int] = None
    service_amount: Optional[int] = None

    order_no: Optional[str] = None       # 키오스크 내부 주문번호
    status: Optional[str] = "APPROVED"   # APPROVED / CANCELED / DECLINED ...

    is_cancel: Optional[bool] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None

    # NICE 응답 관련 (모두 옵션)
    service_code: Optional[str] = None
    reject_code: Optional[str] = None
    response_message: Optional[str] = None

    approved_at: Optional[datetime] = None
    approval_no: Optional[str] = None
    issuer_code: Optional[str] = None
    acquirer_code: Optional[str] = None
    issuer_name: Optional[str] = None
    acquirer_name: Optional[str] = None
    merchant_no: Optional[str] = None
    masked_pan: Optional[str] = None

    pay_kind_code: Optional[str] = None
    pay_type: Optional[str] = None
    terminal_sn: Optional[str] = None
    cat_id: Optional[str] = None
    transaction_id: Optional[str] = None
    balance_amount: Optional[int] = None
    easy_pay_type: Optional[str] = None

    parent_transaction_id: Optional[str] = None
    raw_response: Optional[str] = None
