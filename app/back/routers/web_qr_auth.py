from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..services import qr_auth_service
from ..models.qr_auth import QrAuthStatus

router = APIRouter()
templates = Jinja2Templates(directory="app/back/templates")


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

    # 휴대폰 인증 화면으로 이동
    return templates.TemplateResponse(
        "qr_auth_verify.html",
        {
            "request": request,
            "code": code,
            "session_id": session.id,
            "error": None,
            "info": None,
        },
    )


@router.post("/qr-auth/send-code")
async def qr_auth_send_code(
    request: Request,
    session_id: int = Form(...),
    code: str = Form(...),
    phone: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    휴대폰 번호 입력 후 '인증번호 보내기' 누를 때.
    """
    phone = phone.strip().replace("-", "")

    if not phone.startswith("010") or len(phone) not in (10, 11):
        return templates.TemplateResponse(
            "qr_auth_verify.html",
            {
                "request": request,
                "code": code,
                "session_id": session_id,
                "error": "휴대폰 번호를 정확히 입력해주세요.",
                "info": None,
            },
            status_code=400,
        )

    try:
        session = await qr_auth_service.send_phone_auth_code(
            db=db,
            session_id=session_id,
            phone_number=phone,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "qr_auth_verify.html",
            {
                "request": request,
                "code": code,
                "session_id": session_id,
                "error": str(e),
                "info": None,
            },
            status_code=400,
        )

    return templates.TemplateResponse(
        "qr_auth_verify.html",
        {
            "request": request,
            "code": code,
            "session_id": session.id,
            "error": None,
            "info": "인증번호를 발송했습니다. 문자 메시지를 확인해 주세요.",
        },
    )


@router.post("/qr-auth/complete")
async def qr_auth_complete_from_web(
    request: Request,
    session_id: int = Form(...),
    code: str = Form(...),
    phone: str = Form(...),
    auth_code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    휴대폰 번호 + 인증번호 입력 후 '확인' 눌렀을 때.
    """
    try:
        # 인증번호 검증 및 세션 VERIFIED 처리
        session = await qr_auth_service.verify_phone_auth_code(
            db=db,
            session_id=session_id,
            input_code=auth_code.strip(),
        )
    except ValueError as e:
        return templates.TemplateResponse(
            "qr_auth_verify.html",
            {
                "request": request,
                "code": code,
                "session_id": session_id,
                "error": str(e),
                "info": None,
            },
            status_code=400,
        )

    # 여기까지 오면 kiosk 쪽에서 폴링하던 세션 상태가 VERIFIED로 바뀜
    return templates.TemplateResponse(
        "qr_auth_done.html",
        {"request": request},
    )
