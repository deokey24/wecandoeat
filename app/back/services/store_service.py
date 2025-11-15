from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.models.store import Store, StoreRead, StoreCreate


# ========================
# 전체 지점 조회
# ========================
async def list_stores(db: AsyncSession):
    q = await db.execute(select(Store).order_by(Store.id))
    rows = q.scalars().all()
    return [StoreRead.model_validate(r) for r in rows]


# ========================
# 특정 지점 조회
# ========================
async def get_store(db: AsyncSession, store_id: int):
    q = await db.execute(select(Store).where(Store.id == store_id))
    obj = q.scalar_one_or_none()
    return StoreRead.model_validate(obj) if obj else None


# ========================
# 지점 생성
# ========================
async def create_store(db: AsyncSession, data: StoreCreate):
    store = Store(
        code=data.code,
        name=data.name,
        role=data.role,
        status=data.status,
        business_no=data.business_no,
        cs_phone=data.cs_phone,
        opened_at=data.opened_at,
        closed_at=data.closed_at,
        install_location=data.install_location,
        address=data.address,
        kiosk_admin_pin=data.kiosk_admin_pin,
    )

    db.add(store)
    await db.commit()
    await db.refresh(store)
    return StoreRead.model_validate(store)


# ========================
# 지점 수정
# ========================
async def update_store(db: AsyncSession, store_id: int, data: StoreCreate):
    q = await db.execute(select(Store).where(Store.id == store_id))
    store = q.scalar_one_or_none()

    if not store:
        return None

    store.code = data.code
    store.name = data.name
    store.role = data.role
    store.status = data.status
    store.business_no = data.business_no
    store.cs_phone = data.cs_phone
    store.opened_at = data.opened_at
    store.closed_at = data.closed_at
    store.install_location = data.install_location
    store.address = data.address
    store.kiosk_admin_pin = data.kiosk_admin_pin

    await db.commit()
    await db.refresh(store)
    return StoreRead.model_validate(store)
