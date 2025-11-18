# app/back/routers/web_kiosks.py
from datetime import datetime
import random

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import RedirectResponse
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

templates = Jinja2Templates(directory="app/back/templates")
router = APIRouter()

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
    if not current_user:
        return RedirectResponse("/login", status_code=303)

    # 🔹 권한 및 해당 키오스크 접근 가능 여부 확인
    kiosk = await ensure_kiosk_access(db, kiosk_id, current_user)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "해당 키오스크에 접근할 권한이 없습니다."},
            status_code=403,
        )

    mode = request.query_params.get("mode", "view")

    # 슬롯 + 재고 + 상품 조인 (LEFT OUTER JOIN)
    stmt = (
        select(VendingSlot, VendingSlotProduct, Product)
        .join(
            VendingSlotProduct,
            VendingSlotProduct.slot_id == VendingSlot.id,
            isouter=True,
        )
        .join(
            Product,
            Product.id == VendingSlotProduct.product_id,
            isouter=True,
        )
        .where(VendingSlot.kiosk_id == kiosk.id)
        .order_by(VendingSlot.row, VendingSlot.col)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 층(row)별로 묶기
    layers: dict[int, list[dict]] = {}
    for slot, vsp, product in rows:
        layer = slot.row
        if layer not in layers:
            layers[layer] = []

        label = slot.label or f"{slot.row}-{slot.col}"

        layers[layer].append(
            {
                "slot_id": slot.id,
                "label": label,
                "board_code": slot.board_code,
                "max_capacity": slot.max_capacity,
                "is_enabled": slot.is_enabled,
                "product_id": product.id if product else None,
                "product_name": product.name if product else None,
                "price": product.price if product else None,
                "image_url": product.image_url if product else None,
                "current_stock": vsp.current_stock if vsp else 0,
                "low_stock_alarm": vsp.low_stock_alarm if vsp else 0,
            }
        )

    sorted_layers = sorted(layers.items(), key=lambda x: x[0])

    products = (await db.execute(select(Product))).scalars().all()

    screen_images = sorted(
        kiosk.screen_images,
        key=lambda x: x.sort_order if x.sort_order is not None else 0,
    )

    return templates.TemplateResponse(
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

    await db.commit()
    await kiosk_service.bump_config_version(db, kiosk_id)

    return RedirectResponse(f"/kiosks/{kiosk_id}", status_code=303)




# ---------------------------------------------------------------------------
# 슬롯 배치 / 편집 (상품 매핑 + 용량/재고 설정)
# ---------------------------------------------------------------------------
@router.post("/kiosks/{kiosk_id}/slots/{slot_id}/assign")
async def kiosk_slot_assign(
    kiosk_id: int,
    slot_id: int,
    product_id: int = Form(...),
    max_capacity: int = Form(0),
    current_stock: int = Form(0),
    low_stock_alarm: int = Form(0),
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

    slot_stmt = select(VendingSlot).where(VendingSlot.id == slot_id)
    slot_result = await db.execute(slot_stmt)
    slot = slot_result.scalar_one_or_none()

    if not slot or slot.kiosk_id != kiosk_id:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 슬롯입니다."},
            status_code=404,
        )

    slot.max_capacity = max_capacity
    slot.updated_at = datetime.utcnow()

    vsp_stmt = select(VendingSlotProduct).where(
        VendingSlotProduct.slot_id == slot_id
    )
    vsp_result = await db.execute(vsp_stmt)
    vsp = vsp_result.scalar_one_or_none()

    if vsp is None:
        vsp = VendingSlotProduct(
            slot_id=slot_id,
            product_id=product_id,
            current_stock=current_stock,
            low_stock_alarm=low_stock_alarm,
            is_active=True,
        )
        db.add(vsp)
    else:
        vsp.product_id = product_id
        vsp.current_stock = current_stock
        vsp.low_stock_alarm = low_stock_alarm
        vsp.is_active = True

    await db.commit()
    await kiosk_service.bump_config_version(db, kiosk_id)

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=edit", status_code=303)


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
    await db.commit()

    await kiosk_service.bump_config_version(db, kiosk_id)

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
        await db.commit()

        await kiosk_service.bump_config_version(db, kiosk_id)

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)
