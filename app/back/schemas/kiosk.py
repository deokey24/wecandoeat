# app/back/schemas/kiosk.py
from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class KioskHandshakeRequest(BaseModel):
    kiosk_code: str
    device_uuid: str
    app_version: str


class SlotConfig(BaseModel):
    """
    자판기 슬롯 1칸에 대한 구성 정보 + 매핑된 상품 정보
    """
    # 슬롯 / 보드 위치 정보
    slot_id: int
    board_code: str       # 보드(컨트롤러) 코드 (예: "BOARD1")
    row: int              # 행
    col: int              # 열
    label: Optional[str]  # 사람 눈에 보이는 슬롯 라벨 (예: "A-1")
    max_capacity: int     # 해당 슬롯 최대 수량

    # 매핑된 상품 정보 (없으면 None)
    product_id: Optional[int]
    product_name: Optional[str]
    price: Optional[int]

    # 성인 상품 여부
    is_adult_only: Optional[bool]

    # 이미지 (R2에서 서빙되는 URL)
    image_url: Optional[str] = None        # 리스트/썸네일용
    detail_image_url: Optional[str] = None # 상세 보기용 큰 이미지 (Product.detail_url)

    # 카테고리 (기기 / 코일&카트리지 등)
    # - category_code: 내부 코드 (예: "DEVICE", "CARTRIDGE")
    # - category_name: 화면에 찍을 한글 이름이 따로 필요하면 사용
    category_code: Optional[str] = None
    category_name: Optional[str] = None

    # 현재 재고 (슬롯 기준)
    current_stock: Optional[int]


class KioskConfig(BaseModel):
    kiosk_id: int
    kiosk_name: str
    slots: List[SlotConfig] = []
    screensaver_images: List[str] = []


class KioskHandshakeResponse(BaseModel):
    kiosk_id: int
    store_id: int
    api_key: str          # 키오스크 → 서버 요청 시 사용할 API 키

    # 당장은 평문으로 사용하는 키오스크 비밀번호 (관리자 진입 등)
    # 추후 해시/검증 API 방식으로 교체 예정
    kiosk_password: str

    # 키오스크 구성 정보
    config: KioskConfig


class KioskHeartbeatRequest(BaseModel):
    device_uuid: str
    app_version: str

    board_connected: bool = True           # 자판기 보드 연결 여부
    errors: List[str] = Field(default_factory=list)  # 에러 메시지들

    temperature: Optional[float] = None    # 내부 온도 등
    door_open: Optional[bool] = None       # 문 열림 여부

    # 기타 확장용 필드 (배터리, 네트워크 상태 등 자유롭게)
    extra: Optional[Dict[str, Any]] = None