# app/back/services/product_service.py
from typing import Optional, List

from sqlalchemy import select, func   # ⬅ func 추가
from sqlalchemy.ext.asyncio import AsyncSession
import math                           # ⬅ 페이지 계산용

from app.back.models.product import Product, ProductRead, ProductCreate, ProductUpdate


async def list_products(db: AsyncSession) -> List[ProductRead]:
    result = await db.execute(
        select(Product)
        .where(Product.is_active == True)  # noqa
        .order_by(Product.id)
    )
    rows = result.scalars().all()
    return [ProductRead.model_validate(r) for r in rows]


async def search_products(db: AsyncSession, q: str | None) -> List[ProductRead]:
    stmt = select(Product).where(Product.is_active == True)  # noqa

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Product.name.ilike(like)) | (Product.code.ilike(like))
        )

    stmt = stmt.order_by(Product.id)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [ProductRead.model_validate(r) for r in rows]


# 🔽🔽🔽 여기부터 추가: 페이징 버전
async def search_products_page(
    db: AsyncSession,
    q: str | None,
    page: int,
    page_size: int,
):
    """
    검색 + 페이징 처리
    - page: 1부터 시작
    - page_size: 한 페이지 당 개수
    """
    # 공통 조건
    conditions = [Product.is_active == True]  # noqa

    if q:
        like = f"%{q}%"
        conditions.append(
            (Product.name.ilike(like)) | (Product.code.ilike(like))
        )

    # 전체 개수
    count_stmt = (
        select(func.count())
        .select_from(Product)
        .where(*conditions)
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # 페이지 보정
    if total == 0:
        total_pages = 1
        page = 1
    else:
        total_pages = max(1, math.ceil(total / page_size))
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1

    offset = (page - 1) * page_size

    # 실제 데이터 조각
    list_stmt = (
        select(Product)
        .where(*conditions)
        .order_by(Product.id)
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(list_stmt)
    rows = result.scalars().all()
    items = [ProductRead.model_validate(r) for r in rows]

    has_prev = page > 1
    has_next = page < total_pages

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": has_prev,
        "has_next": has_next,
    }


async def get_product(db: AsyncSession, product_id: int) -> Optional[ProductRead]:
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    obj = result.scalar_one_or_none()
    return ProductRead.model_validate(obj) if obj else None


async def create_product(db: AsyncSession, data: ProductCreate) -> ProductRead:
    product = Product(
        name=data.name,
        price=data.price,
        code=data.code,
        category=data.category,
        is_adult_only=data.is_adult_only,
        image_object_key=data.image_object_key,
        detail_object_key=data.detail_object_key,
        image_url=data.image_url,
        detail_url=data.detail_url,
        description=data.description,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


async def update_product(
    db: AsyncSession,
    product_id: int,
    data: ProductUpdate,
) -> Optional[ProductRead]:
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        return None

    product.name = data.name
    product.price = data.price
    product.code = data.code
    product.category = data.category
    product.is_adult_only = data.is_adult_only
    product.image_url = data.image_url
    product.detail_url = data.detail_url
    product.description = data.description
    product.is_active = data.is_active

    await db.commit()
    await db.refresh(product)
    return ProductRead.model_validate(product)


async def delete_product(db: AsyncSession, product_id: int):
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        return False

    await db.delete(product)
    await db.commit()
    return True
