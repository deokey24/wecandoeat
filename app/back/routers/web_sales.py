# app/back/routers/web_sales.py
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.models.store import Store
from app.back.models.kiosk import Kiosk
from app.back.models.order import Order
from app.back.models.user import UserORM

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
KST = ZoneInfo("Asia/Seoul")
UTC = ZoneInfo("UTC")


# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------
@dataclass
class SalesRow:
    ordered_at: Optional[datetime]
    kiosk_name: str
    product_name: Optional[str]
    quantity: int
    status: Optional[str]
    price: int
    order_no: Optional[str]


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------
def kst_date_range_to_utc(start: date, end: date) -> tuple[datetime, datetime]:
    """
    KST 기준 날짜(start~end)를
    UTC datetime 범위로 변환
    """
    start_kst = datetime.combine(start, time.min).replace(tzinfo=KST)
    end_kst = datetime.combine(end + timedelta(days=1), time.min).replace(tzinfo=KST)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    result = await db.execute(select(UserORM).where(UserORM.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    if user.role != 1:
        store_result = await db.execute(
            select(Store).where(Store.role == user.role)
        )
        user.store = store_result.scalar_one_or_none()
    else:
        user.store = None

    return user


# ---------------------------------------------------------------------------
# 매출 조회
# ---------------------------------------------------------------------------
@router.get("/sales")
async def sales_page(
    request: Request,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_id: Optional[str] = Query(None),
    order_no: Optional[str] = Query(None),
    product_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    role = current_user.role

    # -----------------------------------------------------------------------
    # 기간 기본값 (KST 기준)
    # -----------------------------------------------------------------------
    today = date.today()
    start_date = start_date or today
    end_date = end_date or today

    # ✅ KST → UTC 변환
    start_dt, end_dt = kst_date_range_to_utc(start_date, end_date)

    # -----------------------------------------------------------------------
    # 지점 처리
    # -----------------------------------------------------------------------
    stores: List[Store] = []
    effective_store_id: Optional[int] = None

    if role == 1:
        stores = (await db.execute(select(Store).order_by(Store.name))).scalars().all()
        if store_id:
            try:
                effective_store_id = int(store_id)
            except ValueError:
                pass
    else:
        store = (
            await db.execute(select(Store).where(Store.role == role))
        ).scalar_one_or_none()

        if store:
            stores = [store]
            effective_store_id = store.id

    # -----------------------------------------------------------------------
    # 주문 조회 (✅ approved_at 기준)
    # -----------------------------------------------------------------------
    conditions = [
        Order.approved_at >= start_dt,
        Order.approved_at < end_dt,
    ]

    if effective_store_id is not None:
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
        .order_by(Order.approved_at.desc())
    )

    rows = (await db.execute(stmt)).all()

    # -----------------------------------------------------------------------
    # DTO 변환 (✅ UTC → KST)
    # -----------------------------------------------------------------------
    orders: List[SalesRow] = []

    for order, store, kiosk in rows:
        ordered_at = order.approved_at
        if ordered_at:
            ordered_at = ordered_at.astimezone(KST)

        orders.append(
            SalesRow(
                ordered_at=ordered_at,
                kiosk_name=kiosk.name if kiosk else "",
                product_name=order.product_name,
                quantity=order.quantity or 0,
                status=order.status,
                price=order.price or 0,
                order_no=order.order_no,
            )
        )

    # -----------------------------------------------------------------------
    # 통계
    # -----------------------------------------------------------------------
    total_orders = len(orders)
    total_quantity = sum(o.quantity for o in orders)
    total_sales = sum(o.price for o in orders)
    avg_order_amount = total_sales // total_orders if total_orders else 0

    # -----------------------------------------------------------------------
    # Render
    # -----------------------------------------------------------------------
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
