# app/back/routers/web_kiosks.py
from datetime import datetime
import random

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.back.core.db import get_db
from app.back.core.r2_client import upload_image_to_r2
from app.back.models.kiosk import Kiosk, KioskScreenImage
from app.back.models.store import Store
from app.back.models.vending import VendingSlot, VendingSlotProduct
from app.back.models.product import Product
from app.back.services import kiosk_service, user_service
from app.back.models.kiosk_product import KioskProduct

import time, logging

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()

perf_logger = logging.getLogger("perf.kiosk")  # 성능 로그용 로거

async def generate_unique_pair_code_4(db: AsyncSession) -> str:
    for _ in range(50):  # 안전장치: 최대 50번 시도
        code = f"{random.randint(0, 9999):04d}"  # 0000 ~ 9999

        exists = await db.scalar(
            select(Kiosk.id).where(Kiosk.pair_code_4 == code)
        )
        if not exists:
            return code

    # 이론상 거의 안 오지만, 정말 꽉 찬 경우
    raise HTTPException(status_code=500, detail="고유한 4자리 코드를 생성하지 못했습니다.")

async def ensure_kiosk_access(
    db: AsyncSession,
    kiosk_id: int,
    current_user,
) -> Kiosk | None:
    """
    - 로그인은 이미 된 상태라고 가정
    - role < 1 : 접근 불가
    - role == 1 : 모든 키오스크 접근 가능
    - role >= 2 : Store.role == user.role 인 지점의 키오스크만 접근 가능
    """
    if current_user.role < 1:
        return None

    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk:
        return None

    # 전체 관리자 → 바로 OK
    if current_user.role == 1:
        return kiosk

    # 지점 관리자 → 본인 role 과 store.role 이 같은 경우만 허용
    if kiosk.store and kiosk.store.role == current_user.role:
        return kiosk

    return None


# ---------------------------------------------------------------------------
# 공통: 현재 유저
# ---------------------------------------------------------------------------
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await user_service.get_by_id(db, user_id)


# ---------------------------------------------------------------------------
# 키오스크 목록
# ---------------------------------------------------------------------------
@router.get("/kiosks")
async def kiosks_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # role 0: 대기 / 일반 계정 → 접근 금지
    if current_user.role < 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    # -----------------------------
    # ① 전체 관리자 (role == 1)
    #    → 모든 지점/키오스크 조회
    # -----------------------------
    if current_user.role == 1:
        result = await db.execute(
            select(Kiosk, Store)
            .join(Store, Store.id == Kiosk.store_id)
            .order_by(Store.name, Kiosk.name)
        )

    # -----------------------------
    # ② 지점 관리자 (role >= 2)
    #    → 본인 role 과 같은 Store.role 의 지점만 조회
    #       예: user.role = 3 → Store.role = 3 인 지점
    # -----------------------------
    else:
        result = await db.execute(
            select(Kiosk, Store)
            .join(Store, Store.id == Kiosk.store_id)
            .where(Store.role == current_user.role)
            .order_by(Store.name, Kiosk.name)
        )

    rows = result.all()

    kiosks = []
    for kiosk, store in rows:
        kiosks.append(
            {
                "id": kiosk.id,
                "name": kiosk.name,
                "code": kiosk.code,
                "store_name": store.name,
                "app_version": kiosk.app_version,
                "last_heartbeat_at": kiosk.last_heartbeat_at,
                "is_active": kiosk.is_active,
            }
        )

    return templates.TemplateResponse(
        "kiosks.html",
        {
            "request": request,
            "current_user": current_user,
            "kiosks": kiosks,
        },
    )


# ---------------------------------------------------------------------------
# 키오스크 생성
# ---------------------------------------------------------------------------
@router.get("/kiosks/new")
async def kiosk_new_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    stores = (await db.execute(select(Store))).scalars().all()

    return templates.TemplateResponse(
        "kiosk_new.html",
        {
            "request": request,
            "current_user": current_user,
            "stores": stores,
        },
    )


@router.post("/kiosks/new")
async def kiosk_create(
    request: Request,
    store_id: int = Form(...),
    name: str = Form(...),
    code: str = Form(...),
    kiosk_password: str = Form(...),
    generate_api_key: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )
        
    existing = await db.execute(select(Kiosk).where(Kiosk.code == code))
    if existing.scalar_one_or_none():
        stores = (await db.execute(select(Store))).scalars().all()
        return templates.TemplateResponse(
            "kiosk_new.html",
            {
                "request": request,
                "current_user": current_user,
                "stores": stores,
                "error": "이미 사용 중인 키오스크 코드입니다.",
                "form_name": name,
                "form_code": code,
                "form_store_id": store_id,
            },
            status_code=400,
        )
        
    pair_code_4 = await generate_unique_pair_code_4(db)

    # 1) 키오스크 생성
    kiosk = Kiosk(
        store_id=store_id,
        name=name,
        code=code,
        kiosk_password=kiosk_password,
        api_key=kiosk_service.generate_api_key() if generate_api_key else None,
        is_active=True,
        pair_code_4=pair_code_4,
    )
    db.add(kiosk)
    await db.flush()  # kiosk.id 확보

    # 2) 슬롯 자동 생성 (8단 × 10칸)
    TOTAL_ROWS = 8
    TOTAL_COLS = 10  # 5칸 + 5칸이지만 DB상 col은 1~10 하나로 가자.

    for row in range(1, TOTAL_ROWS + 1):
        row_letter = chr(64 + row)  # 1→A, 2→B, ... 8→H

        for col in range(1, TOTAL_COLS + 1):
            board_code = f"{row_letter}{col:02d}"  # A01 ~ H10
            slot = VendingSlot(
                kiosk_id=kiosk.id,
                row=row,
                col=col,
                board_code=board_code,
                label=f"{row}-{col}",
                max_capacity=0,
                is_enabled=True,
            )
            db.add(slot)
            
    default_screensaver_url = (
        "https://img.wecandoeat.com/kiosk/CHUNCHEON01/screensaver/fbf280035f08418d8b0eb26d40ebc978.png"
    )
    
    default_img = KioskScreenImage(
        kiosk_id=kiosk.id,
        image_url=default_screensaver_url,
        sort_order=1,
        is_active=True,
    )
    db.add(default_img)


    try:
        await db.commit()
    except IntegrityError:
        # ✅ 혹시라도 동시에 같은 코드로 들어온 경우 대비
        await db.rollback()
        stores = (await db.execute(select(Store))).scalars().all()
        return templates.TemplateResponse(
            "kiosk_new.html",
            {
                "request": request,
                "current_user": current_user,
                "stores": stores,
                "error": "키오스크 코드가 중복되었습니다. 다른 코드를 사용해주세요.",
                "form_name": name,
                "form_code": code,
                "form_store_id": store_id,
            },
            status_code=400,
        )


    return RedirectResponse("/kiosks", status_code=303)



# ---------------------------------------------------------------------------
# 키오스크 상세 (하드웨어/슬롯 현황 + 배치 모드)
# ---------------------------------------------------------------------------
@router.get("/kiosks/{kiosk_id}")
async def kiosk_detail_page(
    kiosk_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    start = time.perf_counter()
    perf_logger.info("kiosk_detail[%s]: start", kiosk_id)

    if not current_user:
        perf_logger.info(
            "kiosk_detail[%s]: no current_user (%.3fs)",
            kiosk_id,
            time.perf_counter() - start,
        )
        return RedirectResponse("/login", status_code=303)

    # 🔹 권한 및 해당 키오스크 접근 가능 여부 확인
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    perf_logger.info(
        "kiosk_detail[%s]: after ensure_kiosk_access (%.3fs)",
        kiosk_id,
        time.perf_counter() - start,
    )
    if not kiosk:
        perf_logger.info(
            "kiosk_detail[%s]: forbidden (%.3fs)",
            kiosk_id,
            time.perf_counter() - start,
        )
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    mode = request.query_params.get("mode", "view")

    # 슬롯 + 재고 + 키오스크 전용 상품 스냅샷 조인
    stmt = (
        select(VendingSlot, VendingSlotProduct, KioskProduct)
        .join(
            VendingSlotProduct,
            VendingSlotProduct.slot_id == VendingSlot.id,
            isouter=True,
        )
        .join(
            KioskProduct,
            KioskProduct.id == VendingSlotProduct.kiosk_product_id,
            isouter=True,
        )
        .where(VendingSlot.kiosk_id == kiosk.id)
        .order_by(VendingSlot.row, VendingSlot.col)
    )
    result = await db.execute(stmt)
    rows = result.all()
    perf_logger.info(
        "kiosk_detail[%s]: after slot+vsp+kp query (rows=%d, %.3fs)",
        kiosk_id,
        len(rows),
        time.perf_counter() - start,
    )

    # 층(row)별로 묶기
    layers: dict[int, list[dict]] = {}
    for slot, vsp, kp in rows:
        layer = slot.row
        if layer not in layers:
            layers[layer] = []

        label = slot.label or f"{slot.row}-{slot.col}"

        layers[layer].append(
            {
                "slot_id": slot.id,
                "row": slot.row,
                "col": slot.col,
                "board_code": slot.board_code,
                "label": label,
                "max_capacity": slot.max_capacity,
                # 🔹 모달에서 기본 상품 선택값으로 사용할 것 (마스터 Product ID)
                "product_id": kp.base_product_id if kp else None,
                # 🔹 슬롯에 매핑된 키오스크 전용 상품 ID
                "kiosk_product_id": vsp.kiosk_product_id if vsp else None,
                "product_name": kp.name if kp else None,
                "price": kp.price if kp else None,
                "image_url": kp.image_url if kp else None,
                "current_stock": vsp.current_stock if vsp else 0,
                "low_stock_alarm": vsp.low_stock_alarm if vsp else 0,
            }
        )

    sorted_layers = sorted(layers.items(), key=lambda x: x[0])
    perf_logger.info(
        "kiosk_detail[%s]: after building layers (layers=%d, %.3fs)",
        kiosk_id,
        len(sorted_layers),
        time.perf_counter() - start,
    )

    # 상품 선택 모달에서 사용할 '마스터 Product 목록'
    products = (await db.execute(select(Product))).scalars().all()
    perf_logger.info(
        "kiosk_detail[%s]: after loading products (count=%d, %.3fs)",
        kiosk_id,
        len(products),
        time.perf_counter() - start,
    )

    screen_images = sorted(
        kiosk.screen_images,
        key=lambda x: x.sort_order if x.sort_order is not None else 0,
    )
    perf_logger.info(
        "kiosk_detail[%s]: after loading screen_images (count=%d, %.3fs)",
        kiosk_id,
        len(screen_images),
        time.perf_counter() - start,
    )

    resp = templates.TemplateResponse(
        "kiosk_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "kiosk": kiosk,
            "layers": sorted_layers,
            "products": products,
            "mode": mode,
            "screen_images": screen_images,
        },
    )
    perf_logger.info(
        "kiosk_detail[%s]: end (total %.3fs)",
        kiosk_id,
        time.perf_counter() - start,
    )
    return resp
    


# ---------------------------------------------------------------------------
# 슬롯 재고 +/- 버튼
# ---------------------------------------------------------------------------
@router.post("/kiosks/{kiosk_id}/slots/{slot_id}/stock")
async def kiosk_slot_stock_update(
    kiosk_id: int,
    slot_id: int,
    action: str = Form(...),  # "inc" or "dec"
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    stmt = select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    result = await db.execute(stmt)
    vsp = result.scalar_one_or_none()

    if not vsp:
        return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)

    if action == "inc":
        vsp.current_stock += 1
    elif action == "dec" and vsp.current_stock > 0:
        vsp.current_stock -= 1

    await db.commit()

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)


@router.post("/kiosks/{kiosk_id}/slots/{slot_id}/clear")
async def kiosk_slot_clear(
    kiosk_id: int,
    slot_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    slot = await db.get(VendingSlot, slot_id)
    if not slot or slot.kiosk_id != kiosk_id:
        return RedirectResponse(f"/kiosks/{kiosk_id}", status_code=303)

    result = await db.execute(
        select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    )
    vsp = result.scalar_one_or_none()

    if vsp:
        await db.delete(vsp)

    slot.max_capacity = 0

    # 🔹 config_version 직접 증가
    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.utcnow()

    # 🔹 한 번만 commit
    await db.commit()

    return RedirectResponse(f"/kiosks/{kiosk_id}", status_code=303)





# ---------------------------------------------------------------------------
# 슬롯 배치 / 편집 (상품 매핑 + 용량/재고 설정)
# ---------------------------------------------------------------------------
@router.post("/kiosks/{kiosk_id}/slots/{slot_id}/assign")
async def kiosk_slot_assign(
    kiosk_id: int,
    slot_id: int,
    product_id: int = Form(...),         # 마스터 Product ID
    max_capacity: int = Form(0),
    current_stock: int = Form(0),
    low_stock_alarm: int = Form(0),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    start = time.perf_counter()
    perf_logger.info(
        "slot_assign[%s/%s]: start (product_id=%s)",
        kiosk_id,
        slot_id,
        product_id,
    )

    if not current_user:
        perf_logger.info(
            "slot_assign[%s/%s]: no current_user (%.3fs)",
            kiosk_id,
            slot_id,
            time.perf_counter() - start,
        )
        return RedirectResponse("/login", status_code=303)

    # 🔹 권한 확인
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    perf_logger.info(
        "slot_assign[%s/%s]: after ensure_kiosk_access (%.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )
    if not kiosk:
        perf_logger.info(
            "slot_assign[%s/%s]: forbidden (%.3fs)",
            kiosk_id,
            slot_id,
            time.perf_counter() - start,
        )
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    # 슬롯 존재 & 소속 확인
    slot = await db.get(VendingSlot, slot_id)
    perf_logger.info(
        "slot_assign[%s/%s]: after load slot (%.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )
    if not slot or slot.kiosk_id != kiosk_id:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 슬롯입니다."},
            status_code=404,
        )

    # 마스터 Product 로드
    base_product = await db.get(Product, product_id)
    perf_logger.info(
        "slot_assign[%s/%s]: after load base_product (%.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )
    if not base_product:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 상품입니다."},
            status_code=404,
        )

    # 동일 키오스크 + 동일 base_product 로 이미 생성된 스냅샷이 있는지 확인
    stmt = (
        select(KioskProduct)
        .where(
            KioskProduct.kiosk_id == kiosk_id,
            KioskProduct.base_product_id == base_product.id,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    kiosk_product = result.scalars().first()
    perf_logger.info(
        "slot_assign[%s/%s]: after kiosk_product query (found=%s, %.3fs)",
        kiosk_id,
        slot_id,
        bool(kiosk_product),
        time.perf_counter() - start,
    )

    # 없으면 새로 스냅샷 생성
    if kiosk_product is None:
        kiosk_product = KioskProduct(
            kiosk_id=kiosk_id,
            base_product_id=base_product.id,
            name=base_product.name,
            code=base_product.code,
            category=base_product.category,
            price=base_product.price,
            is_adult_only=base_product.is_adult_only,
            image_url=base_product.image_url,
            detail_url=base_product.detail_url,
            description=base_product.description,
            is_active=base_product.is_active,
        )
        db.add(kiosk_product)
        await db.flush()  # id 확보
        perf_logger.info(
            "slot_assign[%s/%s]: created new kiosk_product(id=%s) (%.3fs)",
            kiosk_id,
            slot_id,
            kiosk_product.id,
            time.perf_counter() - start,
        )

    # 슬롯 용량 갱신
    slot.max_capacity = max_capacity
    slot.updated_at = datetime.utcnow()

    # 슬롯-상품 매핑(vending_slot_products)
    vsp_stmt = select(VendingSlotProduct).where(
        VendingSlotProduct.slot_id == slot_id
    )
    vsp_result = await db.execute(vsp_stmt)
    vsp = vsp_result.scalar_one_or_none()
    perf_logger.info(
        "slot_assign[%s/%s]: after VSP query (exists=%s, %.3fs)",
        kiosk_id,
        slot_id,
        bool(vsp),
        time.perf_counter() - start,
    )

    if vsp is None:
        vsp = VendingSlotProduct(
            slot_id=slot_id,
            kiosk_product_id=kiosk_product.id,
            current_stock=current_stock,
            low_stock_alarm=low_stock_alarm,
            is_active=True,
        )
        db.add(vsp)
    else:
        vsp.kiosk_product_id = kiosk_product.id
        vsp.current_stock = current_stock
        vsp.low_stock_alarm = low_stock_alarm
        vsp.is_active = True

    # 🔹 이 키오스크의 config_version 직접 올리기
    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.utcnow()

    # 🔹 한 번만 commit
    await db.commit()
    perf_logger.info(
        "slot_assign[%s/%s]: after single commit (%.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )

    resp = RedirectResponse(
        f"/kiosks/{kiosk_id}?mode=edit",
        status_code=303,
    )
    perf_logger.info(
        "slot_assign[%s/%s]: end (total %.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )
    return resp


@router.post("/kiosks/{kiosk_id}/slots/{slot_id}/assign-json")
async def kiosk_slot_assign_json(
    kiosk_id: int,
    slot_id: int,
    product_id: int = Form(...),         # 마스터 Product ID
    max_capacity: int = Form(0),
    current_stock: int = Form(0),
    low_stock_alarm: int = Form(0),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    start = time.perf_counter()
    perf_logger.info(
        "slot_assign_json[%s/%s]: start (product_id=%s)",
        kiosk_id,
        slot_id,
        product_id,
    )

    if not current_user:
        return JSONResponse(
            {"ok": False, "error": "로그인이 필요합니다."},
            status_code=401,
        )

    # 🔹 권한 확인 (kiosk 객체 한 번 로드)
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return JSONResponse(
            {"ok": False, "error": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    # 슬롯 존재 & 소속 확인
    slot = await db.get(VendingSlot, slot_id)
    if not slot or slot.kiosk_id != kiosk_id:
        return JSONResponse(
            {"ok": False, "error": "존재하지 않는 슬롯입니다."},
            status_code=404,
        )

    # 마스터 Product 로드
    base_product = await db.get(Product, product_id)
    if not base_product:
        return JSONResponse(
            {"ok": False, "error": "존재하지 않는 상품입니다."},
            status_code=404,
        )

    # 동일 키오스크 + 동일 base_product 로 이미 생성된 스냅샷이 있는지 확인
    stmt = (
        select(KioskProduct)
        .where(
            KioskProduct.kiosk_id == kiosk_id,
            KioskProduct.base_product_id == base_product.id,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    kiosk_product = result.scalars().first()

    # 없으면 새로 스냅샷 생성
    if kiosk_product is None:
        kiosk_product = KioskProduct(
            kiosk_id=kiosk_id,
            base_product_id=base_product.id,
            name=base_product.name,
            code=base_product.code,
            category=base_product.category,
            price=base_product.price,
            is_adult_only=base_product.is_adult_only,
            image_url=base_product.image_url,
            detail_url=base_product.detail_url,
            description=base_product.description,
            is_active=base_product.is_active,
        )
        db.add(kiosk_product)
        await db.flush()  # id 확보

    # 슬롯 용량 갱신
    slot.max_capacity = max_capacity
    slot.updated_at = datetime.utcnow()

    # 슬롯-상품 매핑(vending_slot_products)
    vsp_stmt = select(VendingSlotProduct).where(
        VendingSlotProduct.slot_id == slot_id
    )
    vsp_result = await db.execute(vsp_stmt)
    vsp = vsp_result.scalar_one_or_none()

    if vsp is None:
        vsp = VendingSlotProduct(
            slot_id=slot_id,
            kiosk_product_id=kiosk_product.id,
            current_stock=current_stock,
            low_stock_alarm=low_stock_alarm,
            is_active=True,
        )
        db.add(vsp)
    else:
        vsp.kiosk_product_id = kiosk_product.id
        vsp.current_stock = current_stock
        vsp.low_stock_alarm = low_stock_alarm
        vsp.is_active = True

    # 🔹 config_version 직접 증가 (이미 kiosk를 들고 있으므로)
    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.utcnow()

    await db.commit()
    perf_logger.info(
        "slot_assign_json[%s/%s]: after commit (%.3fs)",
        kiosk_id,
        slot_id,
        time.perf_counter() - start,
    )

    # 프론트에서 슬롯 카드 업데이트에 쓸 데이터만 반환
    return JSONResponse(
        {
            "ok": True,
            "slot_id": slot_id,
            "kiosk_id": kiosk_id,
            "product": {
                "kiosk_product_id": kiosk_product.id,
                "product_id": base_product.id,
                "name": kiosk_product.name,
                "price": kiosk_product.price,
                "image_url": kiosk_product.image_url,
                "is_adult_only": kiosk_product.is_adult_only,
            },
            "stock": {
                "current_stock": current_stock,
                "max_capacity": max_capacity,
                "low_stock_alarm": low_stock_alarm,
            },
        }
    )




@router.post("/kiosks/{kiosk_id}/screensaver/upload")
async def kiosk_screensaver_upload(
    kiosk_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # 🔹 권한 + 해당 키오스크 접근 여부 확인
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    # R2 업로드
    image_url = await upload_image_to_r2(
        file,
        prefix=f"kiosk/{kiosk.code}/screensaver",
    )

    # sort_order = 현재 최대값 + 1
    result = await db.execute(
        select(func.coalesce(func.max(KioskScreenImage.sort_order), 0)).where(
            KioskScreenImage.kiosk_id == kiosk.id
        )
    )
    max_order = result.scalar_one()

    new_img = KioskScreenImage(
        kiosk_id=kiosk.id,
        image_url=image_url,
        sort_order=max_order + 1,
        is_active=True,
    )
    db.add(new_img)

    # 🔹 config_version 직접 증가
    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.utcnow()

    # 🔹 한 번만 commit
    await db.commit()

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)



@router.post("/kiosks/{kiosk_id}/screensaver/{image_id}/delete")
async def kiosk_screensaver_delete(
    kiosk_id: int,
    image_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # 🔹 권한 + 해당 키오스크 접근 여부 확인
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    img_result = await db.execute(
        select(KioskScreenImage).where(
            KioskScreenImage.id == image_id,
            KioskScreenImage.kiosk_id == kiosk_id,
        )
    )
    img = img_result.scalar_one_or_none()
    if img:
        await db.delete(img)

        # 🔹 config_version 직접 증가
        kiosk.config_version = (kiosk.config_version or 0) + 1
        kiosk.updated_at = datetime.utcnow()

        # 🔹 한 번만 commit
        await db.commit()

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)


# ---------------------------------------------------------------------------
# 슬롯에 배치된 "키오스크 전용 상품" 수정 페이지
# ---------------------------------------------------------------------------
@router.get("/kiosks/{kiosk_id}/products/{kiosk_product_id}/edit")
async def kiosk_product_edit_page(
    kiosk_id: int,
    kiosk_product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    kp = await db.get(KioskProduct, kiosk_product_id)
    if not kp or kp.kiosk_id != kiosk_id:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 상품을 찾을 수 없습니다."},
            status_code=404,
        )

    return templates.TemplateResponse(
        "kiosk_product_edit.html",   # 새 템플릿 or 기존 product_edit.html 재활용
        {
            "request": request,
            "kiosk": kiosk,
            "product": kp,           # 템플릿에서 product.name, product.price 등으로 사용
        },
    )


@router.post("/kiosks/{kiosk_id}/products/{kiosk_product_id}/edit")
async def kiosk_product_edit_submit(
    kiosk_id: int,
    kiosk_product_id: int,
    request: Request,
    name: str = Form(...),
    price: int = Form(...),
    code: str | None = Form(None),
    category: str | None = Form(None),
    is_adult_only: bool = Form(False),
    description: str | None = Form(None),
    is_active: bool = Form(True),

    # 파일 업로드 (선택)
    product_image: UploadFile | None = File(None),
    detail_image: UploadFile | None = File(None),

    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    kp = await db.get(KioskProduct, kiosk_product_id)
    if not kp or kp.kiosk_id != kiosk_id:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 상품을 찾을 수 없습니다."},
            status_code=404,
        )

    # ── 1) 기존 이미지 URL을 기본값으로 유지
    image_url = kp.image_url
    detail_url = kp.detail_url

    # ── 2) 상품 이미지 교체 (파일이 새로 올라온 경우에만)
    if product_image and product_image.filename:
        image_url = await upload_image_to_r2(
            product_image,
            prefix=f"kiosk/{kiosk.code}/products",
        )

    # ── 3) 상세 이미지 교체 (파일이 새로 올라온 경우에만)
    if detail_image and detail_image.filename:
        detail_url = await upload_image_to_r2(
            detail_image,
            prefix=f"kiosk/{kiosk.code}/products/detail",
        )

    # ── 4) 나머지 필드 업데이트
    kp.name = name
    kp.price = price
    kp.code = code or None
    kp.category = category or None
    kp.is_adult_only = is_adult_only
    kp.description = description or None
    kp.is_active = is_active
    kp.image_url = image_url
    kp.detail_url = detail_url

    # 🔹 config_version 직접 증가
    kiosk.config_version = (kiosk.config_version or 0) + 1
    kiosk.updated_at = datetime.utcnow()

    # 🔹 한 번만 commit
    await db.commit()

    return RedirectResponse(
        f"/kiosks/{kiosk_id}?mode=edit",
        status_code=303,
    )