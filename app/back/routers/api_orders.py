# app/back/routers/api_orders.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.models.order import Order
from app.back.services import kiosk_service
from app.back.schemas.order import OrderCreate

router = APIRouter()


@router.post("/api/orders")
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    키오스크에서 결제 완료 후 호출하는 주문 저장 API.

    - kiosk_code 로 키오스크 찾고, store_id 는 kiosk.store_id 에서 세팅
    - 나머지 필드는 전부 nullable 이라, 들어온 것만 그대로 저장
    """

    # 1) 키오스크 찾기
    kiosk = await kiosk_service.get_by_code(db, payload.kiosk_code)
    if not kiosk:
        raise HTTPException(status_code=404, detail="Kiosk not found")

    # 2) Order 인스턴스 생성
    order = Order(
        store_id=kiosk.store_id,
        kiosk_id=kiosk.id,
        product_id=payload.product_id,
        product_name=payload.product_name,
        quantity=payload.quantity,
        price=payload.price,
        vat_amount=payload.vat_amount,
        service_amount=payload.service_amount,
        order_no=payload.order_no,
        status=payload.status,
        is_cancel=payload.is_cancel,
        cancel_reason=payload.cancel_reason,
        cancelled_at=payload.cancelled_at,
        service_code=payload.service_code,
        reject_code=payload.reject_code,
        response_message=payload.response_message,
        approved_at=payload.approved_at,
        approval_no=payload.approval_no,
        issuer_code=payload.issuer_code,
        acquirer_code=payload.acquirer_code,
        issuer_name=payload.issuer_name,
        acquirer_name=payload.acquirer_name,
        merchant_no=payload.merchant_no,
        masked_pan=payload.masked_pan,
        pay_kind_code=payload.pay_kind_code,
        pay_type=payload.pay_type,
        terminal_sn=payload.terminal_sn,
        cat_id=payload.cat_id,
        transaction_id=payload.transaction_id,
        balance_amount=payload.balance_amount,
        easy_pay_type=payload.easy_pay_type,
        parent_transaction_id=payload.parent_transaction_id,
        raw_response=payload.raw_response,
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "id": order.id,
        "store_id": order.store_id,
        "kiosk_id": order.kiosk_id,
        "order_no": order.order_no,
        "status": order.status,
    }
