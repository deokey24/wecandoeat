# app/back/services/kiosk_service.py
import secrets
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.back.models.kiosk import Kiosk, KioskStatusLog
from app.back.models.vending import VendingSlot, VendingSlotProduct
from app.back.models.kiosk_product import KioskProduct  # 🔁 Product 대신 KioskProduct
from app.back.schemas.kiosk import KioskConfig, SlotConfig


async def get_by_id(db: AsyncSession, kiosk_id: int) -> Optional[Kiosk]:
    result = await db.execute(
        select(Kiosk)
        .options(
            selectinload(Kiosk.store),
            selectinload(Kiosk.screen_images),
        )
        .where(Kiosk.id == kiosk_id)
    )
    return result.scalar_one_or_none()


async def get_by_code(db: AsyncSession, code: str) -> Optional[Kiosk]:
    result = await db.execute(
        select(Kiosk)
        .options(
            selectinload(Kiosk.screen_images),
        )
        .where(Kiosk.code == code)
    )
    return result.scalar_one_or_none()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


async def update_handshake(
    db: AsyncSession,
    kiosk: Kiosk,
    device_uuid: str,
    app_version: str,
    ip: Optional[str],
):
    kiosk.device_uuid = device_uuid
    kiosk.app_version = app_version
    kiosk.last_ip = ip
    kiosk.last_heartbeat_at = datetime.now(timezone.utc)

    if not kiosk.api_key:
        kiosk.api_key = generate_api_key()

    kiosk.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(kiosk)


async def update_heartbeat(
    db: AsyncSession,
    kiosk: Kiosk,
    app_version: str,
    ip: Optional[str],
    status_payload: dict,
):
    kiosk.app_version = app_version
    kiosk.last_ip = ip
    kiosk.last_heartbeat_at = datetime.now(timezone.utc)
    kiosk.updated_at = datetime.now(timezone.utc)

    log = KioskStatusLog(
        kiosk_id=kiosk.id,
        status="ONLINE",
        payload=status_payload,
    )
    db.add(log)

    await db.commit()
    await db.refresh(kiosk)


async def build_config(db: AsyncSession, kiosk: Kiosk) -> KioskConfig:
    """
    키오스크에 연결된 슬롯 + 슬롯별 상품/재고 구성 정보
    - 내부 데이터는 kiosk_products 스냅샷 기준
    - JSON 구조는 기존 SlotConfig/KioskConfig 그대로 유지
    """
    stmt = (
        select(
            VendingSlot,
            VendingSlotProduct,
            KioskProduct,
        )
        .join(
            VendingSlotProduct,
            VendingSlotProduct.slot_id == VendingSlot.id,
            isouter=True,
        )
        .join(
            KioskProduct,
            KioskProduct.id == VendingSlotProduct.kiosk_product_id,
            isouter=True,
        )
        .where(VendingSlot.kiosk_id == kiosk.id)
    )

    result = await db.execute(stmt)
    rows = result.all()

    slots: List[SlotConfig] = []

    for slot, vsp, kp in rows:
        if vsp and kp:
            # 🔹 슬롯에 상품이 매핑된 경우 (kiosk_product 기준)
            slots.append(
                SlotConfig(
                    slot_id=slot.id,
                    board_code=slot.board_code,
                    row=slot.row,
                    col=slot.col,
                    label=slot.label,
                    max_capacity=slot.max_capacity,

                    # 상품 기본 정보 (이전에 Product에서 가져오던 필드들을 KioskProduct에서 그대로 사용)
                    product_id=kp.id,          # ← 앱에서 쓰는 ID (이제 kiosk_product.id)
                    product_name=kp.name,
                    price=kp.price,

                    # 성인 여부
                    is_adult_only=kp.is_adult_only,

                    # 이미지들
                    image_url=kp.image_url,
                    detail_image_url=kp.detail_url,

                    # 카테고리
                    category_code=kp.category,
                    category_name=kp.category,
                )
            )
        else:
            # 🔹 비어있는 슬롯
            slots.append(
                SlotConfig(
                    slot_id=slot.id,
                    board_code=slot.board_code,
                    row=slot.row,
                    col=slot.col,
                    label=slot.label,
                    max_capacity=slot.max_capacity,

                    product_id=None,
                    product_name=None,
                    price=None,
                    is_adult_only=None,
                    image_url=None,
                    detail_image_url=None,
                    category_code=None,
                    category_name=None,
                )
            )

    # 보호화면 이미지
    screensaver_images: List[str] = []
    if kiosk.screen_images:
        active_images = [i for i in kiosk.screen_images if i.is_active]
        for img in sorted(active_images, key=lambda x: x.sort_order or 0):
            screensaver_images.append(img.image_url)

    return KioskConfig(
        kiosk_id=kiosk.id,
        kiosk_name=kiosk.name,
        slots=slots,
        screensaver_images=screensaver_images,
    )


async def bump_config_version(db: AsyncSession, kiosk_id: int) -> None:
    kiosk = await db.get(Kiosk, kiosk_id)
    if not kiosk:
        return

    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(kiosk)
