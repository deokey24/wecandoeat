# app/back/services/vending_service.py
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.models.vending import VendingSlot, VendingSlotProduct
from app.back.models.product import Product


async def get_kiosk_slots_grouped_by_row(db: AsyncSession, kiosk_id: int):
    """
    해당 키오스크의 슬롯들을 row(단) 기준으로 묶어서 반환.
    템플릿에서 바로 사용할 수 있게 dict[row] = [slot dict ...] 형태.
    """
    stmt = (
        select(VendingSlot)
        .options(
            joinedload(VendingSlot.slot_product).joinedload(VendingSlotProduct.product)
        )
        .where(VendingSlot.kiosk_id == kiosk_id)
        .order_by(VendingSlot.row, VendingSlot.col)
    )
    result = await db.execute(stmt)
    slots: list[VendingSlot] = result.scalars().all()

    layers: dict[int, list[dict]] = {}

    for slot in slots:
        row = slot.row
        link = slot.slot_product
        product: Product | None = link.product if link else None

        data = {
            "slot_id": slot.id,
            "row": slot.row,
            "col": slot.col,
            "board_code": slot.board_code,
            "label": slot.label or f"{slot.row}-{slot.col}",
            "max_capacity": slot.max_capacity,
            "is_enabled": slot.is_enabled,
            "product_id": product.id if product else None,
            "product_name": product.name if product else None,
            "price": product.price if product else None,
            "image_url": product.image_url if product else None,
            "current_stock": link.current_stock if link else 0,
            "low_stock_alarm": link.low_stock_alarm if link else 0,
            "link_is_active": link.is_active if link else False,
        }

        layers.setdefault(row, []).append(data)

    return layers


async def upsert_slot_product(
    db: AsyncSession,
    slot_id: int,
    product_id: int,
    current_stock: int,
    low_stock_alarm: int,
    max_capacity: int,
):
    """슬롯에 상품 매핑(없으면 생성, 있으면 수정) + max_capacity 업데이트"""
    # 슬롯
    res = await db.execute(
        select(VendingSlot).where(VendingSlot.id == slot_id)
    )
    slot = res.scalar_one()
    slot.max_capacity = max_capacity
    slot.updated_at = datetime.utcnow()

    # 링크
    res2 = await db.execute(
        select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    )
    link = res2.scalar_one_or_none()

    if link is None:
        link = VendingSlotProduct(
            slot_id=slot_id,
            product_id=product_id,
            current_stock=current_stock,
            low_stock_alarm=low_stock_alarm,
            is_active=True,
        )
        db.add(link)
    else:
        link.product_id = product_id
        link.current_stock = current_stock
        link.low_stock_alarm = low_stock_alarm
        link.is_active = True

    await db.commit()


async def change_slot_stock(db: AsyncSession, slot_id: int, delta: int):
    """재고 +/-1 같은 용도"""
    res = await db.execute(
        select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    )
    link = res.scalar_one_or_none()
    if link is None:
        # 아직 상품 매핑이 안되어 있으면 무시
        return

    new_stock = link.current_stock + delta
    if new_stock < 0:
        new_stock = 0

    link.current_stock = new_stock
    await db.commit()
