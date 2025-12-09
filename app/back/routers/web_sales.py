# app/back/routers/web_sales.py
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, List

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
# 유틸 / 공용 모델
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


def _to_datetime_range(start: date, end: date) -> tuple[datetime, datetime]:
    """
    [start, end] 일자 구간을 포함하는 datetime 범위로 변환
    """
    start_dt = datetime.combine(start, time.min)
    # end 날짜의 다음날 0시 직전까지 포함
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    return start_dt, end_dt


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    세션에서 user_id를 꺼내 현재 로그인 유저 ORM 객체를 반환.
    + role과 같은 role을 가진 Store를 찾아 current_user.store 로 달아줌.
    (템플릿에서 {{ current_user.store.name }} 사용 때문에)
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    result = await db.execute(select(UserORM).where(UserORM.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None

    # 관리자(role=1)가 아닌 경우: role과 매칭되는 지점 찾아서 user.store에 붙여줌
    if user.role != 1:
        store_result = await db.execute(
            select(Store).where(Store.role == user.role)
        )
        store = store_result.scalar_one_or_none()
        # SQLAlchemy ORM 객체이므로 동적으로 속성 추가 가능
        user.store = store
    else:
        user.store = None

    return user


# ---------------------------------------------------------------------------
# 매출 조회 페이지
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
    # 로그인 체크
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    role = current_user.role

    # -----------------------------------------------------------------------
    # 기간 기본값: 오늘
    # -----------------------------------------------------------------------
    today = date.today()
    if start_date is None:
        start_date = today
    if end_date is None:
        end_date = today

    start_dt, end_dt = _to_datetime_range(start_date, end_date)

    # -----------------------------------------------------------------------
    # 지점 / 권한 처리
    #  - role == 1  : 관리자 → 전체 지점 + 선택 가능
    #  - role != 1  : 해당 role 과 매칭되는 Store.role 의 지점만 조회
    # -----------------------------------------------------------------------
    stores: List[Store] = []
    effective_store_id: Optional[int] = None

    if role == 1:
        # 관리자: 모든 지점 리스트 + 필요 시 store_id 파라미터로 필터
        stores = (await db.execute(select(Store).order_by(Store.name))).scalars().all()
        if store_id:
            try:
                effective_store_id = int(store_id)
            except ValueError:
                effective_store_id = None
    else:
        # 일반 계정: user.role == store.role 로 지점 1개 매칭
        store_row = (
            await db.execute(
                select(Store).where(Store.role == role)
            )
        ).scalar_one_or_none()

        if store_row:
            stores = [store_row]
            effective_store_id = store_row.id
        else:
            # 매칭되는 지점이 없으면 안전하게 어떤 매출도 보여주지 않음
            effective_store_id = None
            stores = []

    # -----------------------------------------------------------------------
    # 주문 목록 조회
    #  - created_at / approved_at 기준 기간 필터
    #  - 관리자: 선택한 지점(effective_store_id) 있으면 해당 지점만
    #  - 지점계정: 본인 지점(effective_store_id)만
    #  - 주문번호 / 상품명 필터
    # -----------------------------------------------------------------------
    conditions = [
        Order.created_at >= start_dt,
        Order.created_at < end_dt,
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
        .order_by(Order.created_at.desc())
    )

    rows = (await db.execute(stmt)).all()

    # -----------------------------------------------------------------------
    # 템플릿에 넘길 주문 DTO 리스트 구성
    # -----------------------------------------------------------------------
    orders: List[SalesRow] = []

    for order, store, kiosk in rows:
        ordered_at = order.approved_at or order.created_at
        kiosk_name = kiosk.name if kiosk else ""
        orders.append(
            SalesRow(
                ordered_at=ordered_at,
                kiosk_name=kiosk_name,
                product_name=order.product_name,
                quantity=order.quantity or 0,
                status=order.status,
                price=order.price or 0,
                order_no=order.order_no,
            )
        )

    # -----------------------------------------------------------------------
    # 통계값 계산
    # -----------------------------------------------------------------------
    total_orders = len(orders)
    total_quantity = sum(o.quantity for o in orders)
    total_sales = sum(o.price for o in orders)
    avg_order_amount = total_sales // total_orders if total_orders > 0 else 0

    # -----------------------------------------------------------------------
    # 렌더링
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
