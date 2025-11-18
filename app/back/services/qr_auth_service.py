from datetime import datetime, timedelta, timezone
from typing import Optional
import random

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.kiosk import Kiosk
from ..models.qr_auth import QrAuthSession, QrAuthStatus
from .sens_sms_service import send_auth_sms

def _generate_auth_code(length: int = 6) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(length))



async def create_session(
    db: AsyncSession,
    kiosk_id: int,
    ttl_sec: int = 300,
) -> QrAuthSession:
    now = datetime.now(timezone.utc)

    kiosk = await db.scalar(
        select(Kiosk).where(Kiosk.id == kiosk_id)
    )
    if not kiosk:
        raise ValueError("Kiosk not found")

    if not kiosk.pair_code_4:
        raise ValueError("Kiosk has no pair_code_4 assigned")

    session = QrAuthSession(
        kiosk_id=kiosk.id,
        status=QrAuthStatus.PENDING,
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_sec),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_by_id(
    db: AsyncSession,
    session_id: int,
) -> Optional[QrAuthSession]:
    return await db.get(QrAuthSession, session_id)


async def set_session_verified(
    db: AsyncSession,
    session_id: int,
    user_id: Optional[int] = None,
) -> QrAuthSession:
    session = await get_session_by_id(db, session_id)
    if not session:
        raise ValueError("Session not found")

    now = datetime.now(timezone.utc)
    if session.expires_at < now:
        session.status = QrAuthStatus.EXPIRED
        await db.commit()
        await db.refresh(session)
        raise ValueError("Session expired")

    session.status = QrAuthStatus.VERIFIED
    session.verified_at = now
    if user_id is not None:
        session.user_id = user_id

    await db.commit()
    await db.refresh(session)
    return session


async def touch_expired(db: AsyncSession, session: QrAuthSession) -> QrAuthSession:
    """만료시간 지나면 상태를 EXPIRED로 바꿔주는 헬퍼 (조회 시 사용)."""
    now = datetime.now(timezone.utc)
    if session.status == QrAuthStatus.PENDING and session.expires_at < now:
        session.status = QrAuthStatus.EXPIRED
        await db.commit()
        await db.refresh(session)
    return session


async def find_latest_pending_session_by_pair_code(
    db: AsyncSession,
    pair_code_4: str,
) -> Optional[QrAuthSession]:
    stmt = (
        select(QrAuthSession)
        .join(Kiosk, QrAuthSession.kiosk_id == Kiosk.id)
        .where(
            Kiosk.pair_code_4 == pair_code_4,
            QrAuthSession.status == QrAuthStatus.PENDING,
        )
        .order_by(desc(QrAuthSession.created_at))
        .limit(1)
    )
    session = await db.scalar(stmt)
    if not session:
        return None
    return await touch_expired(db, session)

async def send_phone_auth_code(
    db: AsyncSession,
    session_id: int,
    phone_number: str,
    ttl_sec: int = 300,
) -> QrAuthSession:
    """
    휴대폰 번호를 받고, 해당 세션에 인증번호를 생성하여 SMS로 발송.
    """
    session = await get_session_by_id(db, session_id)
    if not session:
        raise ValueError("Session not found")

    # 세션 만료/상태 체크
    now = datetime.now(timezone.utc)
    if session.expires_at < now or session.status != QrAuthStatus.PENDING:
        session = await touch_expired(db, session)
        raise ValueError("Session is not valid")

    code = _generate_auth_code()
    session.phone_number = phone_number
    session.sms_code = code
    session.sms_sent_at = now
    # SMS 인증 유효 시간 다시 잡고 싶으면 여기서 expires_at 갱신
    session.expires_at = now + timedelta(seconds=ttl_sec)

    await db.commit()
    await db.refresh(session)

    # 실제 SMS 발송
    await send_auth_sms(phone_number, code)

    return session

async def verify_phone_auth_code(
    db: AsyncSession,
    session_id: int,
    input_code: str,
) -> QrAuthSession:
    """
    사용자가 입력한 인증번호가 맞으면 세션을 VERIFIED로 전환.
    """
    session = await get_session_by_id(db, session_id)
    if not session:
        raise ValueError("Session not found")

    now = datetime.now(timezone.utc)

    # 세션 자체 만료 체크
    if session.expires_at < now:
        session.status = QrAuthStatus.EXPIRED
        await db.commit()
        await db.refresh(session)
        raise ValueError("Session expired")

    if not session.sms_code or not session.phone_number:
        raise ValueError("No auth code sent for this session")

    if session.sms_code != input_code:
        raise ValueError("인증번호가 일치하지 않습니다.")

    # 여기까지 왔으면 인증 성공 → 기존 set_session_verified 와 동일하게 처리
    session.status = QrAuthStatus.VERIFIED
    session.verified_at = now
    # user_id는 아직 없으니 나중에 붙이면 됨 (지금은 None 유지)

    await db.commit()
    await db.refresh(session)
    return session