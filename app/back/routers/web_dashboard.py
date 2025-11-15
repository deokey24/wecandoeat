# app/back/routers/web_dashboard.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import user_service
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/back/templates")

router = APIRouter()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await user_service.get_by_id(db, user_id)


@router.get("/")
async def root(request: Request, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard")
async def dashboard(
    request: Request,
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)
    
    if current_user.role == 0:
    # 승인 대기중 전용 화면 렌더링
        return templates.TemplateResponse(
            "pending.html",
            {"request": request, "user": current_user},
        )

    # 더미 데이터 (나중에 실제 DB 연동)
    today_sales = 123456
    product_count = 42
    store_count = 3
    member_count = 120

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "today_sales": today_sales,
            "product_count": product_count,
            "store_count": store_count,
            "member_count": member_count,
        },
    )
