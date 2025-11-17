# app/back/routers/web_public_files.py
import uuid
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

# ✅ products에서 쓰는 거랑 똑같은 경로로 import 해줘
# 예: web_products.py 상단이 이런 느낌일 거야:
# from app.back.core.r2_client import upload_product_image, build_public_url
from app.back.core.r2_client import upload_product_image, build_public_url  # 경로는 네 프로젝트에 맞게

router = APIRouter(tags=["public-files"])

templates = Jinja2Templates(directory="app/back/templates")  # 다른 web_* 라우터랑 동일하게


@router.get("/public-files")
async def public_files_page(
    request: Request,
    url: str | None = None,
):
    """
    누구나 접근 가능한 파일 업로드 페이지
    - ?url=... 이 있으면 '방금 업로드된 파일 URL'로 보여줌
    """
    return templates.TemplateResponse(
        "public_files.html",
        {
            "request": request,
            "file_url": url,
        },
    )


@router.post("/public-files/upload")
async def public_file_upload(
    request: Request,
    file: UploadFile = File(...),
    prefix: str | None = Form(None),
):
    """
    - 누구나 파일 업로드 가능
    - Cloudflare R2에 저장 (upload_product_image + build_public_url 사용)
    - 업로드 후 공개 URL을 쿼리스트링으로 넘겨서 다시 /public-files 로 이동
    """
    # 파일 바이트 읽기
    file_bytes = await file.read()

    # prefix 없으면 "public/files" 기본값
    base_prefix = (prefix or "public/files").strip("/")

    # 원래 파일 확장자만 유지하고 이름은 uuid로
    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1]

    safe_filename = f"{uuid.uuid4().hex}{ext}"

    # 🔥 여기서 기존 상품 이미지 업로드용 헬퍼 그대로 사용
    # products/new 에서 쓰던 것과 동일 패턴
    # NOTE: 기존 코드에서 await 안 쓰고 있다면 여기도 await 없이 호출해야 함
    object_key = upload_product_image(
        base_prefix,      # 예: "public/files"
        safe_filename,    # 예: "83ac...f.png"
        file_bytes,
    )

    # 공개 URL 만들기
    file_url = build_public_url(object_key)

    # 업로드 후, URL 붙여서 다시 페이지로 리다이렉트
    redirect_url = f"/public-files?url={file_url}"
    return RedirectResponse(url=redirect_url, status_code=303)
