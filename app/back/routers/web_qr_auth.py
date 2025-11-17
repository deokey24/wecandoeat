from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..services import qr_auth_service

router = APIRouter()
templates = Jinja2Templates(directory="app/back/templates")  # 경로는 프로젝트에 맞게 조정


@router.get("/qr-auth")
async def qr_auth_code_page(request: Request):
    """
    고정 QR의 랜딩 페이지.
    - 여기서 4자리 코드를 입력 받음.
    """
    return templates.TemplateResponse(
        "qr_auth_code.html",
        {"request": request, "error": None},
    )


@router.post("/qr-auth")
async def qr_auth_code_submit(
    request: Request,
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    code = code.strip()
    if len(code) != 4 or not code.isdigit():
        return templates.TemplateResponse(
            "qr_auth_code.html",
            {"request": request, "error": "4자리 숫자를 정확히 입력해주세요."},
            status_code=400,
        )

    session = await qr_auth_service.find_latest_pending_session_by_pair_code(db, code)
    if not session:
        return templates.TemplateResponse(
            "qr_auth_code.html",
            {
                "request": request,
                "error": "현재 이 코드로 진행 중인 인증 요청이 없습니다. 키오스크에서 다시 시도해주세요.",
            },
            status_code=400,
        )

    # 여기서는 아직 실제 본인인증/로그인은 안 붙이고
    # "인증 완료" 버튼만 있는 페이지로 넘겨서 흐름만 확인
    return templates.TemplateResponse(
        "qr_auth_verify.html",
        {
            "request": request,
            "code": code,
            "session_id": session.id,
        },
    )


@router.post("/qr-auth/complete")
async def qr_auth_complete_from_web(
    request: Request,
    session_id: int = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # 여기서 원래는 "본인인증 성공 시"에만 들어오게 해야 함.
    try:
        await qr_auth_service.set_session_verified(
            db=db,
            session_id=session_id,
            user_id=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return templates.TemplateResponse(
        "qr_auth_done.html",
        {"request": request},
    )
