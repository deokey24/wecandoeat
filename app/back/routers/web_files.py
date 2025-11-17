# back/routers/web_files.py
import os

from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from back.core.db import get_db
from back.core.security import get_current_user  # 로그인/권한 체크용(프로젝트에 맞게)
from back.services import file_service

router = APIRouter(tags=["files"])

# ⚠️ 경로는 기존 web_* 라우터에서 쓰는 templates 경로와 동일하게 맞춰줘
templates = Jinja2Templates(directory="back/templates")

# 업로드 디렉토리 – 필요시 config에서 가져오도록 바꿔도 됨
UPLOAD_DIR = "/var/data/uploads"


@router.get("/files")
async def files_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    파일 업로드/다운로드 페이지
    """
    # 예: 유저의 store_id 기준으로 필터링하고 싶으면 current_user.store_id 사용
    store_id = getattr(current_user, "store_id", None)

    files = await file_service.list_files(db, store_id=store_id)

    return templates.TemplateResponse(
        "files.html",
        {
            "request": request,
            "files": files,
            "current_user": current_user,
        },
    )


@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    store_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # store_id를 폼에서 선택하게 할 수도 있고,
    # 현재 로그인된 유저의 store_id를 강제할 수도 있음.
    if store_id is None:
        store_id = getattr(current_user, "store_id", None)

    asset = await file_service.save_file(
        db=db,
        upload_dir=UPLOAD_DIR,
        file=file,
        store_id=store_id,
    )

    # 업로드 후 다시 목록 페이지로
    return RedirectResponse(
        url="/files",
        status_code=303,
    )


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    asset = await file_service.get_file_or_none(db, file_id)
    if not asset:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(asset.path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # 다운로드 응답
    return FileResponse(
        path=asset.path,
        media_type=asset.content_type or "application/octet-stream",
        filename=asset.original_name,
    )
