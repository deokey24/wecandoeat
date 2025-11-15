# app/back/routers/web_products.py
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import user_service
from app.back.services import product_service
from app.back.models.product import ProductCreate, ProductUpdate

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()


# 공통: 현재 로그인 유저
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await user_service.get_by_id(db, user_id)


def require_manager(current_user):
    # role >= 1 만 접근 허용 (1=전체관리자, 2이상=지점 담당자)
    return current_user and current_user.role >= 1


# ===========================
# 상품 목록 + 검색
# ===========================
@router.get("/products")
async def products_page(
    request: Request,
    q: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    products = await product_service.search_products(db, q or "")

    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "current_user": current_user,
            "products": products,
            "query": q or "",
        },
    )


# ===========================
# 상품 등록 폼
# ===========================
@router.get("/products/new")
async def new_product_page(
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "product_new.html",
        {
            "request": request,
            "current_user": current_user,
        },
    )


# ===========================
# 상품 등록 처리
# ===========================
@router.post("/products/new")
async def new_product_submit(
    request: Request,
    name: str = Form(...),
    price: int = Form(...),
    code: str | None = Form(None),
    category: str | None = Form(None),
    is_adult_only: bool = Form(False),
    image_url: str | None = Form(None),
    detail_url: str | None = Form(None),
    description: str | None = Form(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    data = ProductCreate(
        name=name,
        price=price,
        code=code or None,
        category=category or None,
        is_adult_only=is_adult_only,
        image_url=image_url or None,
        detail_url=detail_url or None,
        description=description or None,
    )

    await product_service.create_product(db, data)
    return RedirectResponse("/products", status_code=303)


# ===========================
# 상품 수정 폼
# ===========================
@router.get("/products/{product_id}/edit")
async def edit_product_page(
    product_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    product = await product_service.get_product(db, product_id)
    if not product:
        return RedirectResponse("/products", status_code=303)

    return templates.TemplateResponse(
        "product_edit.html",
        {
            "request": request,
            "current_user": current_user,
            "product": product,
        },
    )


# ===========================
# 상품 수정 처리
# ===========================
@router.post("/products/{product_id}/edit")
async def edit_product_submit(
    product_id: int,
    request: Request,
    name: str = Form(...),
    price: int = Form(...),
    code: str | None = Form(None),
    category: str | None = Form(None),
    is_adult_only: bool = Form(False),
    image_url: str | None = Form(None),
    detail_url: str | None = Form(None),
    description: str | None = Form(None),
    is_active: bool = Form(True),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    data = ProductUpdate(
        name=name,
        price=price,
        code=code or None,
        category=category or None,
        is_adult_only=is_adult_only,
        image_url=image_url or None,
        detail_url=detail_url or None,
        description=description or None,
        is_active=is_active,
    )

    await product_service.update_product(db, product_id, data)
    return RedirectResponse("/products", status_code=303)
