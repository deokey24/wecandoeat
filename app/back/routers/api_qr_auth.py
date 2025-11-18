from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.kiosk import Kiosk

from ..core.db import get_db
from ..schemas.qr_auth import (
    QrAuthSessionCreateRequest,
    QrAuthSessionCreateResponse,
    QrAuthSessionStatusResponse,
    QrAuthSessionCompleteRequest,
)
from ..services import qr_auth_service
from ..models.qr_auth import QrAuthStatus

router = APIRouter(prefix="/api/qr-auth", tags=["qr-auth"])


@router.post("/session", response_model=QrAuthSessionCreateResponse)
async def create_qr_auth_session(
    payload: QrAuthSessionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    키오스크가 "인증 시작" 누를 때 호출.
    - kiosk_id, ttl_sec 받아서 세션 생성
    - session_id / 해당 kiosk의 4자리 코드 / 만료시간 반환
    """
    try:
        session = await qr_auth_service.create_session(
            db=db,
            kiosk_id=payload.kiosk_id,
            ttl_sec=payload.ttl_sec,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    kiosk = await db.scalar(
        select(Kiosk).where(Kiosk.id == session.kiosk_id)
    )
    if not kiosk or not kiosk.pair_code_4:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kiosk has no pair_code_4",
        )


    return QrAuthSessionCreateResponse(
        session_id=session.id,
        pair_code_4=kiosk.pair_code_4,
        expires_at=session.expires_at,
    )


@router.get("/session/{session_id}/status", response_model=QrAuthSessionStatusResponse)
async def get_qr_auth_session_status(
    session_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    키오스크에서 2~3초마다 폴링하는 상태 조회 API.
    """
    session = await qr_auth_service.get_session_by_id(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 만료 체크
    session = await qr_auth_service.touch_expired(db, session)

    return QrAuthSessionStatusResponse(
        status=session.status.value,
        expires_at=session.expires_at,
        verified_at=session.verified_at,
    )


@router.post("/session/{session_id}/complete")
async def complete_qr_auth_session(
    session_id: int,
    payload: QrAuthSessionCompleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    휴대폰에서 인증이 끝났을 때(본인인증/로그인 성공 후) 호출.
    """
    try:
        await qr_auth_service.set_session_verified(
            db=db,
            session_id=session_id,
            user_id=payload.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"ok": True}
