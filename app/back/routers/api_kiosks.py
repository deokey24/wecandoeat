# app/back/routers/api_kiosks.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.schemas.kiosk import (
    KioskHandshakeRequest,
    KioskHandshakeResponse,
    KioskHeartbeatRequest,
    KioskInventoryUpdateRequest,
    KioskInventoryUpdateResult,
    KioskInventorySnapshot
)
from app.back.services import kiosk_service, vending_service

router = APIRouter(prefix="/api/kiosks", tags=["kiosk-api"])


@router.post("/handshake", response_model=KioskHandshakeResponse)
async def kiosk_handshake(
    payload: KioskHandshakeRequest,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    kiosk = await kiosk_service.get_by_code(db, payload.kiosk_code)
    if not kiosk or not kiosk.is_active:
        raise HTTPException(status_code=403, detail="Kiosk not allowed")

    client_ip = request.client.host if request and request.client else None

    await kiosk_service.update_handshake(
        db,
        kiosk,
        device_uuid=payload.device_uuid,
        app_version=payload.app_version,
        ip=client_ip,
    )

    config = await kiosk_service.build_config(db, kiosk)

    return KioskHandshakeResponse(
        kiosk_id=kiosk.id,
        store_id=kiosk.store_id,
        api_key=kiosk.api_key,
        kiosk_password=kiosk.kiosk_password,
        pairing_code=kiosk.pair_code_4,
        config_version=kiosk.config_version,
        config=config,
    )


@router.post("/{kiosk_id}/heartbeat")
async def kiosk_heartbeat(
    kiosk_id: int,
    payload: KioskHeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    x_kiosk_api_key: str = Header(default=None),
    request: Request = None,
):
    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk or not kiosk.is_active:
        raise HTTPException(status_code=403, detail="Kiosk not allowed")

    if not x_kiosk_api_key or kiosk.api_key != x_kiosk_api_key:
        raise HTTPException(status_code=401, detail="Invalid kiosk api key")

    client_ip = request.client.host if request and request.client else None

    await kiosk_service.update_heartbeat(
        db,
        kiosk,
        app_version=payload.app_version,
        ip=client_ip,
        status_payload=payload.model_dump(),
    )

    # 🔹 설정 업데이트 필요 여부 계산
    has_config_update = False
    if payload.current_config_version is not None:
        if payload.current_config_version < (kiosk.config_version or 1):
            has_config_update = True

    # 🔹 필요할 때만 config 내려주기 (필드 추가라서 기존 앱과 완전 호환)
    config = None
    if has_config_update:
        config = await kiosk_service.build_config(db, kiosk)

    return {
        "ok": True,
        "server_time": datetime.now(timezone.utc).isoformat(),
        "config_version": kiosk.config_version,
        "has_config_update": has_config_update,
        "config": config,  # ← 새 앱에서 사용할 수 있는 필드
    }
    
# =============================
# 3) 재고 업데이트
# =============================
@router.post("/{kiosk_id}/inventory", response_model=KioskInventoryUpdateResult)
async def kiosk_inventory_update(
    kiosk_id: int,
    payload: KioskInventoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    x_kiosk_api_key: str = Header(default=None),
    request: Request = None,
):
    """
    키오스크 앱 → 서버 재고 동기화 API

    - mode="partial": 전달된 슬롯들만 재고 업데이트
    - mode="replace": 이 요청을 '전체 재고 스냅샷'으로 보고,
                      나머지 슬롯은 재고 0 으로 처리
    """
    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk or not kiosk.is_active:
        raise HTTPException(status_code=403, detail="Kiosk not allowed")

    if not x_kiosk_api_key or kiosk.api_key != x_kiosk_api_key:
        raise HTTPException(status_code=401, detail="Invalid kiosk api key")

    # Just for completeness (추후 로그에 활용 가능)
    client_ip = request.client.host if request and request.client else None
    # 현재는 client_ip 따로 쓰진 않지만 필요하면 kiosk.last_ip 갱신에 활용 가능

    # service 에서 쓰기 쉽게 dict 리스트로 변환
    items = [
        {
            "slot_id": item.slot_id,
            "current_stock": item.current_stock,
            "low_stock_alarm": item.low_stock_alarm,
        }
        for item in payload.items
    ]

    if payload.mode == "replace":
        updated, skipped = await vending_service.update_inventory_replace(
            db=db,
            kiosk_id=kiosk_id,
            items=items,
        )
    else:
        # default: partial
        updated, skipped = await vending_service.update_inventory_partial(
            db=db,
            kiosk_id=kiosk_id,
            items=items,
        )

    return KioskInventoryUpdateResult(
        ok=True,
        updated=updated,
        skipped=skipped,
        mode=payload.mode,
    )

@router.get(
    "/{kiosk_id}/inventory",
    response_model=KioskInventorySnapshot,
)
async def get_kiosk_inventory(
    kiosk_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    키오스크 → 서버
    - 현재 서버에 저장된 슬롯별 재고를 조회해서
      앱 측 재고를 동기화하기 위한 엔드포인트.

    인증:
    - path 의 kiosk_id + 헤더의 X-Kiosk-Api-Key 로 검증
    """

    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk or not kiosk.is_active:
        raise HTTPException(status_code=403, detail="Kiosk not allowed")

    # (필요하다면 여기서 last_ip, last_heartbeat_at 업데이트 가능)
    client_ip = request.client.host if request and request.client else None
    # TODO: 필요하면 kiosk.last_ip = client_ip 등 갱신 로직 추가

    items = await vending_service.get_inventory_snapshot(
        db=db,
        kiosk_id=kiosk_id,
    )

    return KioskInventorySnapshot(
        kiosk_id=kiosk_id,
        items=items,
    )

# =============================
# 🔹 원격배출 전용 핑 (앱에서 10초마다 호출)
# =============================

class RemotePingRequest(BaseModel):
    kiosk_code: str | None = None  # 있으면 검증, 없어도 api_key만으로 통과 가능하도록


class RemotePingResponse(BaseModel):
    ok: bool
    remote_vend_slot_id: int | None = None
    server_time: str


@router.post("/{kiosk_id}/remote-ping", response_model=RemotePingResponse)
async def kiosk_remote_ping(
    kiosk_id: int,
    payload: RemotePingRequest,
    db: AsyncSession = Depends(get_db),
    x_kiosk_api_key: str = Header(default=None),
    request: Request = None,  # ← 그냥 Request 타입 + 기본값만 None
):
    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk or not kiosk.is_active:
        raise HTTPException(status_code=403, detail="Kiosk not allowed")

    if not x_kiosk_api_key or kiosk.api_key != x_kiosk_api_key:
        raise HTTPException(status_code=401, detail="Invalid kiosk api key")

    # kiosk_code 체크 넣고 싶으면 여기에

    remote_vend_slot_id = kiosk_service.pop_remote_vend_slot(kiosk.id)

    return RemotePingResponse(
        ok=True,
        remote_vend_slot_id=remote_vend_slot_id,
        server_time=datetime.now(timezone.utc).isoformat(),
    )
