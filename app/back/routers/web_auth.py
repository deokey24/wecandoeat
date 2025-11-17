# app/back/routers/web_auth.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import user_service

from fastapi.templating import Jinja2Templates
from app.back.models.user import UserCreate

templates = Jinja2Templates(directory="app/back/templates")

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await user_service.authenticate(db, username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "아이디 또는 비밀번호가 올바르지 않습니다.",
            },
            status_code=400,
        )

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["name"] = user.name
    request.session["role"] = user.role

    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None},
    )
    
@router.post("/register")
async def register_submit(
    request: Request,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # 1) 비밀번호 확인 체크
    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "비밀번호와 비밀번호 확인이 일치하지 않습니다.",
            },
            status_code=400,
        )

    # 2) 유저 생성 시도
    try:
        user_in = UserCreate(
            name=name,
            username=username,
            password=password,
            # 관리자 권한은 폼에서 제거했으니 여기서는 기본값으로 False
            is_admin=False,
        )
        await user_service.create_user(db, user_in)

    except ValueError as e:
        # 예: 이미 존재하는 아이디일 때 user_service에서 ValueError 발생
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": str(e),
            },
            status_code=400,
        )

    # 3) 성공 시 로그인 페이지로 이동
    return RedirectResponse(url="/login", status_code=303)
