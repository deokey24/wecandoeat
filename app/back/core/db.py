# app/back/core/db.py
import re
import urllib.parse

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
)
from sqlalchemy.orm import sessionmaker, declarative_base

from app.back.core.config import settings

# 1) Settings 에서 원본 DATABASE_URL 가져오기
RAW_DATABASE_URL = settings.DATABASE_URL

# 2) sslmode, channel_binding 같은 querystring 제거
parsed = urllib.parse.urlsplit(RAW_DATABASE_URL)
# query 부분을 날린 새 URL
clean_url = urllib.parse.urlunsplit(parsed._replace(query=""))

# 3) postgresql: → postgresql+asyncpg: 로 변경
ASYNC_DATABASE_URL = re.sub(r"^postgresql:", "postgresql+asyncpg:", clean_url)

# 4) asyncpg + SSL 설정으로 엔진 생성
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,        # 필요하면 True로 바꿔서 SQL 로그 보기
    future=True,
    connect_args={
        "ssl": "require",   # Neon 이 SSL 요구하므로 이렇게 지정
    },
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


async def get_db():
    """FastAPI 의존성용 세션"""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """
    초기 개발 단계용: 모델 변경 시마다 테이블 자동 생성.
    나중에는 Alembic 마이그레이션으로 교체하는 게 좋음.
    """
    async with engine.begin() as conn:
        # 여기서 import 해야 순환참조 방지
        from app.back.models.user import UserORM

        await conn.run_sync(Base.metadata.create_all)
