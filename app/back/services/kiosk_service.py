# app/back/services/kiosk_service.py
import secrets
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.back.models.kiosk import Kiosk, KioskStatusLog, KioskScreenImage
from app.back.models.vending import VendingSlot, VendingSlotProduct
from app.back.models.product import Product
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
        select(Kiosk).
        options(
            selectinload(Kiosk.screen_images),
        )
        .where(Kiosk.code == code))
    return result.scalar_one_or_none()


def generate_api_key() -> str:
    # 설치 시 생성할 키오스크 전용 API Key
    return secrets.token_urlsafe(32)


async def update_handshake(
    db: AsyncSession,
    kiosk: Kiosk,
    device_uuid: str,
    app_version: str,
    ip: Optional[str],
):
    """핸드셰이크 시 키오스크 기본 정보 업데이트"""
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
    """하트비트 수신 시 상태 업데이트 + 로그 기록"""
    kiosk.app_version = app_version
    kiosk.last_ip = ip
    kiosk.last_heartbeat_at = datetime.now(timezone.utc)
    kiosk.updated_at = datetime.now(timezone.utc)

    log = KioskStatusLog(
        kiosk_id=kiosk.id,
        status="ONLINE",
        payload=str(status_payload),
    )
    db.add(log)

    await db.commit()
    await db.refresh(kiosk)


async def build_config(db: AsyncSession, kiosk: Kiosk) -> KioskConfig:
    """
    키오스크에 연결된 슬롯 + 슬롯별 상품/재고 구성 정보
    """
    stmt = (
        select(
            VendingSlot,
            VendingSlotProduct,
            Product,
        )
        .join(
            VendingSlotProduct,
            VendingSlotProduct.slot_id == VendingSlot.id,
            isouter=True,
        )
        .join(
            Product,
            Product.id == VendingSlotProduct.product_id,
            isouter=True,
        )
        .where(VendingSlot.kiosk_id == kiosk.id)
    )

    result = await db.execute(stmt)
    rows = result.all()

    slots: List[SlotConfig] = []

    for slot, vsp, product in rows:
        if vsp and product:
            slots.append(
                SlotConfig(
                    slot_id=slot.id,
                    board_code=slot.board_code,
                    row=slot.row,
                    col=slot.col,
                    label=slot.label,
                    max_capacity=slot.max_capacity,

                    # 상품 기본 정보
                    product_id=product.id,
                    product_name=product.name,
                    price=product.price,

                    # ★ 성인여부
                    is_adult_only=product.is_adult_only,

                    # ★ 이미지들
                    image_url=product.image_url,
                    detail_image_url=product.detail_url,

                    # ★ 카테고리 (기기 / 카트리지)
                    category_code=product.category,
                    category_name=product.category,   # 혹시 한글명 따로 있으면 매핑 가능

                    # 재고
                    current_stock=vsp.current_stock,
                )
            )
        else:
            slots.append(
                SlotConfig(
                    slot_id=slot.id,
                    board_code=slot.board_code,
                    row=slot.row,
                    col=slot.col,
                    label=slot.label,
                    max_capacity=slot.max_capacity,

                    # 비어있는 슬롯
                    product_id=None,
                    product_name=None,
                    price=None,
                    is_adult_only=None,
                    image_url=None,
                    detail_image_url=None,
                    category_code=None,
                    category_name=None,
                    current_stock=None,
                )
            )

    # 보호화면 이미지
    screensaver_images: List[str] = []
    if kiosk.screen_images:
        for img in sorted(
            [i for i in kiosk.screen_images if i.is_active],
            key=lambda x: x.sort_order,
        ):
            screensaver_images.append(img.image_url)

    return KioskConfig(
        kiosk_id=kiosk.id,
        kiosk_name=kiosk.name,
        slots=slots,
        screensaver_images=screensaver_images,
    )
