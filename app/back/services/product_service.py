# app/back/services/product_service.py
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
