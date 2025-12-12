# app/back/routers/web_kiosk_logs.py

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.models.store import Store
from app.back.models.kiosk import Kiosk, KioskEventLog
from app.back.models.user import UserORM

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()


# ---------------------------------------------------------------------------
# 유틸 / 공용 모델
# ---------------------------------------------------------------------------

@dataclass
class KioskEventRow:
    log: KioskEventLog
    kiosk: Optional[Kiosk]
    store: Optional[Store]


def _to_datetime_range(start: date, end: date) -> tuple[datetime, datetime]:
    """
    [start, end] 일자 구간을 포함하는 datetime 범위로 변환
    (end 날짜의 다음날 0시까지)
    """
    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)
    return start_dt, end_dt


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    web_sales.py 와 동일한 패턴:
    - 세션에서 user_id 가져옴
    - UserORM 조회
    - role != 1 이면 role 과 같은 Store 를 찾아 user.store 에 달아줌
    """
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
        store = store_result.scalar_one_or_none()
        user.store = store
    else:
        user.store = None

    return user


# ---------------------------------------------------------------------------
# 결제/배출 로그 페이지 (관리자 전용)
# ---------------------------------------------------------------------------

@router.get("/kiosk-logs")
async def kiosk_logs_page(
    request: Request,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    store_id: Optional[str] = Query(None),   # 🔹 문자열로 받기
    kiosk_id: Optional[str] = Query(None),   # 🔹 문자열로 받기
    event_name: Optional[str] = Query("PAY_VEND_FAIL"),
    reason: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # 로그인 체크
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    role = current_user.role

    # 관리자(role=1)만 접근 가능
    if role != 1:
        return RedirectResponse("/dashboard", status_code=303)

    # -----------------------------------------------------------------------
    # 기간 기본값: 오늘
    # -----------------------------------------------------------------------
    today = date.today()
    if date_from is None:
        date_from = today
    if date_to is None:
        date_to = today

    start_dt, end_dt = _to_datetime_range(date_from, date_to)

    # -----------------------------------------------------------------------
    # 지점 / 키오스크 목록 (필터용)
    # -----------------------------------------------------------------------
    stores: List[Store] = (
        await db.execute(select(Store).order_by(Store.name))
    ).scalars().all()
    kiosks: List[Kiosk] = (
        await db.execute(select(Kiosk).order_by(Kiosk.id))
    ).scalars().all()

    # 문자열 → int 변환 (빈 문자열/이상한 값은 None 처리)
    effective_store_id: Optional[int] = None
    if store_id:
        try:
            effective_store_id = int(store_id)
        except ValueError:
            effective_store_id = None

    effective_kiosk_id: Optional[int] = None
    if kiosk_id:
        try:
            effective_kiosk_id = int(kiosk_id)
        except ValueError:
            effective_kiosk_id = None

    # -----------------------------------------------------------------------
    # 기본 쿼리 (로그 + 키오스크 + 지점 조인)
    # -----------------------------------------------------------------------
    base_stmt = (
        select(KioskEventLog, Kiosk, Store)
        .join(Kiosk, Kiosk.id == KioskEventLog.kiosk_id, isouter=True)
        .join(Store, Store.id == Kiosk.store_id, isouter=True)
        .where(KioskEventLog.occurred_at >= start_dt)
        .where(KioskEventLog.occurred_at < end_dt)
    )

    if effective_store_id is not None:
        base_stmt = base_stmt.where(Store.id == effective_store_id)

    if effective_kiosk_id is not None:
        base_stmt = base_stmt.where(Kiosk.id == effective_kiosk_id)

    if event_name and event_name != "ALL":
        base_stmt = base_stmt.where(KioskEventLog.event_name == event_name)

    if reason:
        like_pattern = f"%{reason.strip()}%"
        base_stmt = base_stmt.where(KioskEventLog.reason.ilike(like_pattern))

    # -----------------------------------------------------------------------
    # 전체 개수
    # -----------------------------------------------------------------------
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one() or 0

    # -----------------------------------------------------------------------
    # 페이지네이션 적용
    # -----------------------------------------------------------------------
    offset = (page - 1) * page_size
    stmt = (
        base_stmt
        .order_by(KioskEventLog.occurred_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    rows = (await db.execute(stmt)).all()

    logs: List[KioskEventRow] = []
    for log, kiosk_obj, store_obj in rows:
        logs.append(
            KioskEventRow(
                log=log,
                kiosk=kiosk_obj,
                store=store_obj,
            )
        )

    selected_event_name = event_name if event_name else "PAY_VEND_FAIL"
    selected_reason = reason or ""

    return templates.TemplateResponse(
        "kiosk_logs.html",
        {
            "request": request,
            "current_user": current_user,
            "role": role,
            "stores": stores,
            "kiosks": kiosks,
            "logs": logs,
            "total": total,
            "page": page,
            "page_size": page_size,
            "date_from": date_from,
            "date_to": date_to,
            "selected_store_id": effective_store_id,
            "selected_kiosk_id": effective_kiosk_id,
            "selected_event_name": selected_event_name,
            "selected_reason": selected_reason,
        },
    )
