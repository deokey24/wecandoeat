# app/back/schemas/qr_auth.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class QrAuthSessionCreateRequest(BaseModel):
    """
    키오스크가 'QR 인증 세션 생성' 요청할 때 사용하는 바디.
    """
    kiosk_id: int
    ttl_sec: int = Field(default=300, ge=60, le=3600)  # 1분~1시간


class QrAuthSessionCreateResponse(BaseModel):
    """
    세션 생성 API 응답.
    - session_id: 키오스크가 폴링할 때 사용할 ID
    - pair_code_4: 화면에 보여줄 4자리 코드 (kiosk.pair_code_4)
    - expires_at: 세션 만료 시각
    """
    session_id: int
    pair_code_4: str
    expires_at: datetime


class QrAuthSessionStatusResponse(BaseModel):
    """
    키오스크가 /status 폴링할 때 받는 응답.
    """
    status: str            # "PENDING", "VERIFIED", "EXPIRED", "CANCELLED"
    expires_at: datetime
    verified_at: Optional[datetime] = None


class QrAuthSessionCompleteRequest(BaseModel):
    """
    휴대폰 쪽(웹)에서 '인증 완료' 처리할 때 넘겨줄 정보.
    지금은 user_id만 선택적으로, 나중에 확장 가능.
    """
    user_id: Optional[int] = None
