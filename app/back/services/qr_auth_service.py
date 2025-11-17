from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.kiosk import Kiosk
from ..models.qr_auth import QrAuthSession, QrAuthStatus


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
