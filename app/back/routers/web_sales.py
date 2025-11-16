# app/back/routers/web_sales.py
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.models.store import Store
from app.back.models.kiosk import Kiosk
from app.back.models.order import Order
from app.back.services import user_service

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()


# ---------------------------------------------------------------------------
# 공통: 현재 유저
# (web_kiosks.py 에서 쓰는 패턴 그대로)
# ---------------------------------------------------------------------------
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await user_service.get_by_id(db, user_id)


def _to_datetime_range(d_from: date, d_to: date) -> tuple[datetime, datetime]:
    """
    날짜 두 개를 받아서 [from, to+1일) 형태의 datetime 범위로 변환
    (created_at 기준으로 필터링)
    """
    start_dt = datetime.combine(d_from, time.min)
    end_dt = datetime.combine(d_to + timedelta(days=1), time.min)
    return start_dt, end_dt


# ---------------------------------------------------------------------------
# 매출 조회 페이지
# ---------------------------------------------------------------------------
@router.get("/sales")
async def sales_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    # 쿼리 파라미터
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_id: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    product_name: Optional[str] = Query(None),
):
    # 로그인 체크
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    role = current_user.role

    # 기본 기간: 오늘
    today = date.today()
    if start_date is None:
        start_date = today
    if end_date is None:
        end_date = today

    start_dt, end_dt = _to_datetime_range(start_date, end_date)

    # -----------------------------------------------------------------------
    # 지점 선택 처리
    # -----------------------------------------------------------------------
    stores = []
    effective_store_id: Optional[int] = None

    if role == 1:
        # 관리자: 모든 지점 리스트 + 선택 가능
        stores = (await db.execute(select(Store))).scalars().all()
        if store_id:
            try:
                effective_store_id = int(store_id)
            except ValueError:
                effective_store_id = None
    else:
        # 지점 담당자: 자기 지점만 조회
        # user.store_id 있다고 가정 (없으면 여기 로직만 프로젝트에 맞게 조정)
        effective_store_id = getattr(current_user, "store_id", None)

    # -----------------------------------------------------------------------
    # 주문 목록 조회
    # created_at 기준 기간 필터,
    # 필요시 store_id, order_no, product_name 필터
    # -----------------------------------------------------------------------
    conditions = [
        Order.created_at >= start_dt,
        Order.created_at < end_dt,
    ]

    if effective_store_id:
        conditions.append(Order.store_id == effective_store_id)

    if order_no:
        conditions.append(Order.order_no.ilike(f"%{order_no.strip()}%"))

    if product_name:
        conditions.append(Order.product_name.ilike(f"%{product_name.strip()}%"))

    stmt = (
        select(Order, Store, Kiosk)
        .join(Store, Store.id == Order.store_id, isouter=True)
        .join(Kiosk, Kiosk.id == Order.kiosk_id, isouter=True)
        .where(and_(*conditions))
        .order_by(Order.created_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    orders = []
    total_orders = 0
    total_quantity = 0
    total_sales = 0

    for order, store, kiosk in rows:
        total_orders += 1

        qty = order.quantity or 0
        price = order.price or 0

        total_quantity += qty
        total_sales += qty * price

        ordered_at = order.approved_at or order.created_at

        orders.append(
            {
                "ordered_at": ordered_at,
                "store_name": store.name if store else "",
                "kiosk_name": kiosk.name if kiosk else "",
                "product_name": order.product_name or "",
                "quantity": qty,
                "status": order.status or "",
                "price": price,
                "order_no": order.order_no or "",
            }
        )

    avg_order_amount = 0
    if total_orders > 0:
        avg_order_amount = total_sales // total_orders

    return templates.TemplateResponse(
        "sales.html",
        {
            "request": request,
            "current_user": current_user,
            "role": role,
            "stores": stores,
            "orders": orders,
            "start_date": start_date,
            "end_date": end_date,
            "selected_store_id": effective_store_id,
            "order_no": order_no or "",
            "product_name": product_name or "",
            "total_orders": total_orders,
            "total_quantity": total_quantity,
            "total_sales": total_sales,
            "avg_order_amount": avg_order_amount,
        },
    )
