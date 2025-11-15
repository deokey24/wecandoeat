# app/back/services/user_service.py
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.back.models.user import UserORM, User, UserCreate
from app.back.core.security import hash_password, verify_password


async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(
        select(UserORM).where(UserORM.id == user_id)
    )
    user_orm = result.scalar_one_or_none()
    if not user_orm:
        return None
    return User.model_validate(user_orm)


async def get_by_username(db: AsyncSession, username: str) -> Optional[UserORM]:
    result = await db.execute(
        select(UserORM).where(UserORM.username == username)
    )
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, user_in: UserCreate) -> User:
    existing = await get_by_username(db, user_in.username)
    if existing:
        raise ValueError("이미 존재하는 아이디입니다.")

    user_orm = UserORM(
        name=user_in.name,
        username=user_in.username,
        password_hash=hash_password(user_in.password),
        is_admin=user_in.is_admin,
        is_active=True,
    )
    db.add(user_orm)
    await db.commit()
    await db.refresh(user_orm)

    return User.model_validate(user_orm)


async def authenticate(
    db: AsyncSession,
    username: str,
    password: str,
) -> Optional[User]:
    user_orm = await get_by_username(db, username)
    if not user_orm:
        return None
    if not user_orm.is_active:
        return None

    if not verify_password(password, user_orm.password_hash):
        return None

    return User.model_validate(user_orm)

async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(UserORM).order_by(UserORM.id))
    rows = result.scalars().all()
    return [User.model_validate(u) for u in rows]

async def update_user_role(
    db: AsyncSession,
    user_id: int,
    new_role: int,
) -> Optional[User]:
    # DB에서 해당 유저 존재 여부 확인
    result = await db.execute(
        select(UserORM).where(UserORM.id == user_id)
    )
    user_orm = result.scalar_one_or_none()
    if not user_orm:
        return None

    user_orm.role = new_role
    # role == 1이면 is_admin도 맞춰주기
    user_orm.is_admin = (new_role == 1)

    db.add(user_orm)
    await db.commit()
    await db.refresh(user_orm)
    return User.model_validate(user_orm)