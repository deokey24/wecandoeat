# app/back/routers/api_kiosks.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import get_db
from app.back.schemas.kiosk import (
    KioskHandshakeRequest,
    KioskHandshakeResponse,
    KioskHeartbeatRequest,
)
from app.back.services import kiosk_service

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
        config=config.model_dump(),
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
        status_payload=payload.dict(),
    )

    return {
        "ok": True,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
