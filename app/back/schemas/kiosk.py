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
    (재고 정보는 포함하지 않음)
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


class KioskConfig(BaseModel):
    kiosk_id: int
    kiosk_name: str
    # 기본값은 빈 리스트 (mutable default는 default_factory 사용)
    slots: List[SlotConfig] = Field(default_factory=list)
    screensaver_images: List[str] = Field(default_factory=list)


class KioskHandshakeResponse(BaseModel):
    kiosk_id: int
    store_id: int
    api_key: str          # 키오스크 → 서버 요청 시 사용할 API 키

    # 당장은 평문으로 사용하는 키오스크 비밀번호 (관리자 진입 등)
    # 추후 해시/검증 API 방식으로 교체 예정
    kiosk_password: str

    pairing_code: str

    config_version: int

    # 키오스크 구성 정보 (재고 없음)
    config: KioskConfig


class KioskHeartbeatRequest(BaseModel):
    device_uuid: str
    app_version: str

    board_connected: bool = True                      # 자판기 보드 연결 여부
    errors: List[str] = Field(default_factory=list)   # 에러 메시지들

    temperature: Optional[float] = None               # 내부 온도 등
    door_open: Optional[bool] = None                  # 문 열림 여부

    current_config_version: Optional[int] = None      # 앱이 들고 있는 설정 버전

    # 기타 확장용 필드 (배터리, 네트워크 상태 등 자유롭게)
    extra: Optional[Dict[str, Any]] = None


class InventoryItem(BaseModel):
    """
    자판기 한 슬롯의 재고 정보.
    - slot_id: handshake/config 에서 내려준 slot_id 를 그대로 사용
    - current_stock: 현재 실제 재고 개수
    - low_stock_alarm: (선택) 이 값 이하로 내려가면 알림/표시용
    """
    slot_id: int
    current_stock: int = Field(ge=0)
    low_stock_alarm: Optional[int] = Field(default=None, ge=0)


class KioskInventoryUpdateRequest(BaseModel):
    """
    재고 업데이트 요청
    - mode = "partial": 전달된 슬롯만 업데이트 (부분 수정)
    - mode = "replace": 이 요청이 '전체 스냅샷'이라고 보고,
                        전달되지 않은 슬롯은 재고 0 으로 간주
    """
    mode: str = Field("partial", pattern="^(partial|replace)$")
    items: List[InventoryItem]


class KioskInventoryUpdateResult(BaseModel):
    ok: bool = True
    updated: int
    skipped: int
    mode: str

class KioskInventorySnapshot(BaseModel):
    """
    키오스크 전체 슬롯 재고 조회 응답
    """
    kiosk_id: int
    items: List[InventoryItem]