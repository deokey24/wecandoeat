# app/back/services/sens_sms_service.py
import base64
import hashlib
import hmac
import time
from typing import Any, Dict

import httpx

from app.back.core.config import settings


def _make_signature(timestamp: str, uri: str) -> str:
    """
    NCP SENS v2 시그니처 생성
    docs: https://api.ncloud-docs.com/docs/ai-application-service-sens-smsv2

    ⚠ 여기서는 한글 절대 안 들어가게!
    method / uri / timestamp / access_key 는 전부 ASCII만 사용하는 값이어야 함.
    """
    access_key = settings.NCP_SENS_ACCESS_KEY  # str (영문/숫자)
    secret_key = settings.NCP_SENS_SECRET_KEY  # str (영문/숫자)

    method = "POST"

    # message: "POST {uri}\n{timestamp}\n{accessKey}"
    message = f"{method} {uri}\n{timestamp}\n{access_key}"

    # UTF-8 로 명시적으로 바이트 변환 (내부는 어차피 ASCII라 문제 없음)
    message_bytes = message.encode("utf-8")
    secret_bytes = secret_key.encode("utf-8")

    signing_key = hmac.new(secret_bytes, message_bytes, digestmod=hashlib.sha256).digest()
    signature = base64.b64encode(signing_key).decode("utf-8")
    return signature


async def send_auth_sms(to_phone: str, auth_code: str) -> Dict[str, Any]:
    """
    인증번호 SMS 발송

    :param to_phone: 수신 번호 (하이픈 없이, 예: 01012345678)
    :param auth_code: 전송할 인증번호 문자열
    """
    if not settings.NCP_SENS_ACCESS_KEY or not settings.NCP_SENS_SECRET_KEY:
        raise RuntimeError("NCP SENS 설정이 올바르지 않습니다.")

    service_id = settings.NCP_SENS_SERVICE_ID
    if not service_id:
        raise RuntimeError("NCP_SENS_SERVICE_ID 가 설정되어 있지 않습니다.")

    # ✅ 여기까지는 전부 ASCII 값만 사용
    uri = f"/sms/v2/services/{service_id}/messages"
    url = f"https://sens.apigw.ntruss.com{uri}"

    timestamp = str(int(time.time() * 1000))

    signature = _make_signature(timestamp, uri)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "x-ncp-apigw-timestamp": timestamp,
        "x-ncp-iam-access-key": settings.NCP_SENS_ACCESS_KEY,
        "x-ncp-apigw-signature-v2": signature,
    }

    # 🔥 여기 content 에는 한글 포함 OK (UTF-8 JSON 으로 나감)
    content = f"[전자담배24시] 인증번호 [{auth_code}]를 입력해 주세요."

    body = {
        "type": "SMS",
        "contentType": "COMM",
        "countryCode": "82",
        "from": settings.NCP_SENS_CALLING_NUMBER,
        "content": content,
        "messages": [
            {"to": to_phone}
        ],
    }

    # httpx 가 body를 JSON → UTF-8 로 인코딩해줌 (ascii 아님)
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        # NCP 에러 있을 수 있으니, 에러내용 보려고 raise_for_status 유지
        resp.raise_for_status()
        return resp.json()
