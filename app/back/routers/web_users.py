from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import user_service
from app.back.services import store_service   # ★ store 서비스 추가

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


@router.get("/users")
async def users_page(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=303)

    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {
                "request": request,
                "message": "권한이 없습니다. 관리자에게 문의하세요.",
            },
            status_code=403,
        )

    users = await user_service.list_users(db)
    stores = await store_service.list_stores(db)   # ★ 지점 목록 추가

    # 기본 role 라벨
    role_labels = {
        0: "가입대기중",
        1: "전체관리자",
        # 2 이상은 DB 기반으로 표시
    }

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "stores": stores,     # ★ 템플릿 전달
            "role_labels": role_labels,
        },
    )


@router.post("/users/{user_id}/role")
async def change_user_role(
    user_id: int,
    request: Request,
    new_role: int = Form(...),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {
                "request": request,
                "message": "권한이 없습니다. 관리자에게 문의하세요.",
            },
            status_code=403,
        )

    await user_service.update_user_role(db, user_id, new_role)

    return RedirectResponse(url="/users", status_code=303)
