# back/models/file_asset.py
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, BigInteger, ForeignKey
from sqlalchemy.orm import relationship

from app.back.core.db import Base  # 기존 Base import 방식 그대로 맞춰줘


class FileAsset(Base):
    __tablename__ = "file_assets"

    id = Column(Integer, primary_key=True, index=True)
    # 필요 없으면 store_id는 지워도 됨
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)

    original_name = Column(String(255), nullable=False)
    saved_name = Column(String(255), nullable=False)  # 실제 서버에 저장된 파일명
    content_type = Column(String(100), nullable=True)
    size = Column(BigInteger, nullable=True)

    # 저장 경로(또는 R2 URL 등) – 여기서는 로컬 상대경로 예시
    path = Column(String(500), nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    store = relationship("Store", back_populates="file_assets", lazy="selectin")
