from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import store_service
from app.back.services import user_service
from sqlalchemy import select, update, delete, and_, or_
from app.back.models.store import Store
from app.back.models.kiosk import Kiosk, KioskScreenImage, KioskStatusLog
from app.back.models.vending import VendingSlot, VendingSlotProduct
from app.back.models.order import Order


templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await user_service.get_by_id(db, user_id)


# 지점 목록 페이지
@router.get("/stores")
async def stores_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # 관리자: 전체 지점
    if current_user.role == 1:
        result = await db.execute(
            select(Store).order_by(Store.id)
        )
        stores = result.scalars().all()

    # 그 외: 본인의 role에 매칭된 지점만
    else:
        result = await db.execute(
            select(Store)
            .where(Store.role == current_user.role)
            .order_by(Store.id)
        )
        stores = result.scalars().all()

    return templates.TemplateResponse(
        "stores.html",
        {
            "request": request,
            "stores": stores,
        },
    )


# 지점 생성
@router.post("/stores/new")
async def create_store(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # 관리자만 등록 가능
    if current_user.role != 1:
        return RedirectResponse("/stores", status_code=303)

    form = await request.form()
    code = form.get("code")
    name = form.get("name")
    status = form.get("status") or "OPEN"
    cs_phone = form.get("cs_phone")
    address = form.get("address")
    store_role = form.get("store_role")

    # 숫자로 변환 + 최소값 체크
    try:
        store_role_int = int(store_role)
        if store_role_int <= 1:
            raise ValueError()
    except Exception:
        # 에러 처리 (템플릿에 error 메시지 넘겨도 됨)
        return RedirectResponse("/stores", status_code=303)

    new_store = Store(
        code=code,
        name=name,
        status=status,
        cs_phone=cs_phone,
        address=address,
        role=store_role_int,
    )
    db.add(new_store)
    await db.commit()

    return RedirectResponse("/stores", status_code=303)

# 🔥 지점 삭제 (관리자 전용)
@router.post("/stores/{store_id}/delete")
async def delete_store(
    store_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    if current_user.role != 1:
        return RedirectResponse("/stores", status_code=303)

    # 1) 존재하는 지점인지 확인
    store_result = await db.execute(select(Store).where(Store.id == store_id))
    store = store_result.scalar_one_or_none()
    if not store:
        return RedirectResponse("/stores", status_code=303)

    # ⚠️ 2) 연관 데이터 순서대로 삭제
    # (실제 테이블 이름/모델은 프로젝트 기준으로 맞춰야 함)

    # 2-1) 이 지점의 키오스크들 조회
    kiosks_result = await db.execute(select(Kiosk).where(Kiosk.store_id == store_id))
    kiosks = kiosks_result.scalars().all()
    kiosk_ids = [k.id for k in kiosks]

    if kiosk_ids:
        # 2-2) 슬롯 관련 데이터 먼저 삭제
        await db.execute(
            delete(VendingSlotProduct).where(VendingSlotProduct.slot_id.in_(
                select(VendingSlot.id).where(VendingSlot.kiosk_id.in_(kiosk_ids))
            ))
        )

        await db.execute(
            delete(VendingSlot).where(VendingSlot.kiosk_id.in_(kiosk_ids))
        )

        # 2-3) 키오스크 상태로그 / 스크린 이미지
        await db.execute(
            delete(KioskStatusLog).where(KioskStatusLog.kiosk_id.in_(kiosk_ids))
        )
        await db.execute(
            delete(KioskScreenImage).where(KioskScreenImage.kiosk_id.in_(kiosk_ids))
        )

        # 2-4) 해당 지점/키오스크의 주문 삭제
        await db.execute(
            delete(Order).where(
                (Order.store_id == store_id) | (Order.kiosk_id.in_(kiosk_ids))
            )
        )

        # 2-5) 키오스크 삭제
        await db.execute(delete(Kiosk).where(Kiosk.id.in_(kiosk_ids)))

    else:
        # 키오스크는 없지만 주문만 있을 수도 있음
        await db.execute(delete(Order).where(Order.store_id == store_id))

    # 3) 마지막으로 지점 삭제
    await db.execute(delete(Store).where(Store.id == store_id))

    await db.commit()

    return RedirectResponse("/stores", status_code=303)