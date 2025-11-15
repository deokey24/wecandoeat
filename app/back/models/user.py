# app/back/models/user.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Boolean, Column, Integer, String, DateTime

from app.back.core.db import Base


# SQLAlchemy ORM 모델 (Postgres 테이블)
class UserORM(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    
    role = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


# ===== Pydantic 스키마들 =====

class User(BaseModel):
    id: int
    name: str
    username: str
    is_active: bool = True
    is_admin: bool = False
    role: int = 0  

    class Config:
        from_attributes = True  # ORM 객체에서 바로 변환 가능


class UserCreate(BaseModel):
    name: str
    username: str
    password: str
    is_admin: bool = False
    role: int = 0


class UserLogin(BaseModel):
    username: str
    password: str
