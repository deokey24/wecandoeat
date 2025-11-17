# app/back/routers/web_products.py

from fastapi import (
    APIRouter,
    Request,
    Depends,
    Form,
    UploadFile,
    File,
    Query,
)
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.services import user_service
from app.back.services import product_service
from app.back.models.product import ProductCreate, ProductUpdate
from app.back.core.r2_client import upload_product_image, build_public_url

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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    page_data = await product_service.search_products_page(
        db=db,
        q=q or "",
        page=page,
        page_size=size,
    )

    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "current_user": current_user,
            "products": page_data["items"],
            "query": q or "",
            "page": page_data["page"],
            "page_size": page_data["page_size"],
            "total": page_data["total"],
            "total_pages": page_data["total_pages"],
            "has_prev": page_data["has_prev"],
            "has_next": page_data["has_next"],
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
# 상품 등록 처리 (이미지 파일만)
# ===========================
@router.post("/products/new")
async def new_product_submit(
    request: Request,
    name: str = Form(...),
    price: int = Form(...),
    code: str | None = Form(None),
    category: str | None = Form(None),
    is_adult_only: bool = Form(False),
    description: str | None = Form(None),

    # 상품 이미지 (필수)
    product_image: UploadFile = File(...),
    # 상세 이미지 (선택)
    detail_image: UploadFile | None = File(None),

    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    # 1) 상품 이미지 R2 업로드
    product_bytes = await product_image.read()
    image_object_key = upload_product_image(
        "products/images",
        product_image.filename,
        product_bytes,
    )
    image_url = build_public_url(image_object_key)

    # 2) 상세 이미지 R2 업로드 (선택)
    detail_object_key: str | None = None
    detail_url: str | None = None

    if detail_image and detail_image.filename:
        detail_bytes = await detail_image.read()
        detail_object_key = upload_product_image(
            "products/details",
            detail_image.filename,
            detail_bytes,
        )
        detail_url = build_public_url(detail_object_key)

    # 3) Pydantic 모델 생성
    data = ProductCreate(
        name=name,
        price=price,
        code=code or None,
        category=category or None,
        is_adult_only=is_adult_only,
        description=description or None,
        image_object_key=image_object_key,
        detail_object_key=detail_object_key,
        image_url=image_url,
        detail_url=detail_url,
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
# 상품 수정 처리 (이미지 교체 지원)
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
    description: str | None = Form(None),
    is_active: bool = Form(True),

    # 새 이미지 업로드 (선택)
    product_image: UploadFile | None = File(None),
    detail_image: UploadFile | None = File(None),

    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    # 기존 상품 정보 조회 (기존 이미지 유지 목적)
    existing = await product_service.get_product(db, product_id)
    if not existing:
        return RedirectResponse("/products", status_code=303)

    # 기본값: 기존 값 유지
    image_object_key: str | None = existing.image_object_key
    detail_object_key: str | None = existing.detail_object_key
    image_url: str | None = existing.image_url
    detail_url: str | None = existing.detail_url

    # 1) 상품 이미지 교체 (파일이 새로 올라온 경우)
    if product_image and product_image.filename:
        product_bytes = await product_image.read()
        image_object_key = upload_product_image(
            "products/images",
            product_image.filename,
            product_bytes,
        )
        image_url = build_public_url(image_object_key)

    # 2) 상세 이미지 교체 (파일이 새로 올라온 경우)
    if detail_image and detail_image.filename:
        detail_bytes = await detail_image.read()
        detail_object_key = upload_product_image(
            "products/details",
            detail_image.filename,
            detail_bytes,
        )
        detail_url = build_public_url(detail_object_key)

    data = ProductUpdate(
        name=name,
        price=price,
        code=code or None,
        category=category or None,
        is_adult_only=is_adult_only,
        description=description or None,
        is_active=is_active,
        image_object_key=image_object_key,
        detail_object_key=detail_object_key,
        image_url=image_url,
        detail_url=detail_url,
    )

    await product_service.update_product(db, product_id, data)
    return RedirectResponse("/products", status_code=303)

@router.post("/products/{product_id}/delete")
async def delete_product(
    product_id: int,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not require_manager(current_user):
        return RedirectResponse("/login", status_code=303)

    await product_service.delete_product(db, product_id)
    return RedirectResponse("/products", status_code=303)