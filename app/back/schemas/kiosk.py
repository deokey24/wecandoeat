# app/back/schemas/kiosk.py
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class KioskHandshakeRequest(BaseModel):
    kiosk_code: str
    device_uuid: str
    app_version: str


class SlotConfig(BaseModel):
    slot_id: int
    board_code: str
    row: int
    col: int
    label: Optional[str]
    max_capacity: int

    product_id: Optional[int]
    product_name: Optional[str]
    price: Optional[int]
    is_adult_only: Optional[bool]
    image_url: Optional[str]
    current_stock: Optional[int]


class KioskConfig(BaseModel):
    kiosk_id: int
    kiosk_name: str
    slots: List[SlotConfig] = []


class KioskHandshakeResponse(BaseModel):
    kiosk_id: int
    store_id: int
    api_key: str
    config: KioskConfig


class KioskHeartbeatRequest(BaseModel):
    device_uuid: str
    app_version: str
    board_connected: bool = True
    errors: List[str] = []
    temperature: Optional[float] = None
    door_open: Optional[bool] = None
    extra: Optional[dict] = None
