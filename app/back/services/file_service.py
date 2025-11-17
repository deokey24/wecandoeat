# back/services/file_service.py
import os
import uuid
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from back.models.file_asset import FileAsset


# 업로드 기본 디렉토리 (예시)
DEFAULT_UPLOAD_DIR = "/var/data/uploads"


async def list_files(
    db: AsyncSession,
    store_id: Optional[int] = None,
) -> List[FileAsset]:
    stmt = select(FileAsset).order_by(FileAsset.id.desc())
    if store_id is not None:
        stmt = stmt.where(FileAsset.store_id == store_id)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_file_or_none(db: AsyncSession, file_id: int) -> Optional[FileAsset]:
    stmt = select(FileAsset).where(FileAsset.id == file_id)
    result = await db.execute(stmt)
    return result.scalars().first()


async def save_file(
    db: AsyncSession,
    upload_dir: str,
    file,
    store_id: Optional[int] = None,
) -> FileAsset:
    """
    - file: fastapi.UploadFile
    - upload_dir: 실제 저장할 디렉토리
    """
    os.makedirs(upload_dir, exist_ok=True)

    # 고유 파일명 생성
    ext = os.path.splitext(file.filename or "")[1]
    saved_name = f"{uuid.uuid4().hex}{ext}"

    saved_path = os.path.join(upload_dir, saved_name)

    # 실제 파일 저장
    # UploadFile은 async file이지만 여기선 간단히 read() 사용 예시
    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    size = len(content)

    # DB 기록
    asset = FileAsset(
        store_id=store_id,
        original_name=file.filename or saved_name,
        saved_name=saved_name,
        content_type=file.content_type,
        size=size,
        path=saved_path,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset
