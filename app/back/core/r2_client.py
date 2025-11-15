# app/back/core/r2_client.py
import os
import uuid
import mimetypes

from typing import Any

import boto3
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_ID = os.getenv("CF_R2_ACCOUNT_ID")
ACCESS_KEY = os.getenv("CF_R2_ACCESS_KEY_ID")
SECRET_KEY = os.getenv("CF_R2_SECRET_ACCESS_KEY")
BUCKET_NAME = os.getenv("CF_R2_BUCKET_NAME")
PUBLIC_BASE_URL = os.getenv("CF_R2_PUBLIC_BASE_URL")  # 선택 (CDN/도메인 붙였으면)

# R2 S3 호환 엔드포인트
endpoint_url = f"https://{ACCOUNT_ID}.r2.cloudflarestorage.com"

s3 = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)


def _guess_content_type(filename: str) -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "application/octet-stream"


def upload_product_image(prefix: str, filename: str, data: bytes) -> str:
    """
    상품 이미지/상세이미지 업로드용
    prefix: "products/images" / "products/details" 등
    return: object_key (예: "products/images/abcd1234.jpg")
    """
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = ""

    object_key = f"{prefix}/{uuid.uuid4().hex}{ext}"
    content_type = _guess_content_type(filename)

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=object_key,
        Body=data,
        ContentType=content_type,
    )

    return object_key


def build_public_url(object_key: str) -> str:
    """
    R2 object key -> 외부에서 접근 가능한 URL
    """
    if PUBLIC_BASE_URL:
        base = PUBLIC_BASE_URL.rstrip("/")
        return f"{base}/{object_key}"

    return f"{endpoint_url}/{BUCKET_NAME}/{object_key}"

async def upload_image_to_r2(file: Any, prefix: str) -> str:
    """
    FastAPI UploadFile 같은 객체를 받아서 R2에 업로드하고
    '외부에서 접근 가능한 URL'을 바로 반환하는 헬퍼.

    사용 예:
        image_url = await upload_image_to_r2(file, "kiosk/GANGNAM01/screensaver")
    """
    # file 은 보통 fastapi.UploadFile 형태라고 가정 (.filename, .read() 지원)
    original_filename = getattr(file, "filename", "upload.bin")
    data = await file.read()

    # 기존 상품 업로드 유틸 재사용 (object_key 반환)
    object_key = upload_product_image(prefix=prefix, filename=original_filename, data=data)

    # 외부 접근 가능한 URL로 변환해서 반환
    public_url = build_public_url(object_key)
    return public_url