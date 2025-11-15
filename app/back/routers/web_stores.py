from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import store_service
from app.back.services import user_service
from sqlalchemy import select, update, delete, and_, or_
from app.back.models.store import Store


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
