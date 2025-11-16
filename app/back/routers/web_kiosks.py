# app/back/routers/web_kiosks.py
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    result = await db.execute(
        select(Kiosk, Store)
        .join(Store, Store.id == Kiosk.store_id)
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

    # 1) 키오스크 생성
    kiosk = Kiosk(
        store_id=store_id,
        name=name,
        code=code,
        kiosk_password=kiosk_password,
        api_key=kiosk_service.generate_api_key() if generate_api_key else None,
        is_active=True,
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
        "https://pub-2e3bf3debf45436a98ca36200e74fd66.r2.dev/kiosk/CHUNCHEON01/screensaver/fbf280035f08418d8b0eb26d40ebc978.png"
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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    mode = request.query_params.get("mode", "view")

    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 키오스크입니다."},
            status_code=404,
        )

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
        layer = slot.row  # 1,2,3,...층
        if layer not in layers:
            layers[layer] = []

        label = slot.label or f"{slot.row}-{slot.col}"  # 예: 1-1, 1-2 ...

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

    # row 번호 순으로 정렬된 리스트 형태로 변환
    sorted_layers = sorted(layers.items(), key=lambda x: x[0])  # [(1, [...]), (2,[...])]

    # 상품 목록 (지점별로 나눌 거면 여기서 store_id로 필터)
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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    # 해당 슬롯 + 재고 가져오기
    stmt = select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    result = await db.execute(stmt)
    vsp = result.scalar_one_or_none()

    if not vsp:
        # 상품 매핑이 아직 없다면 아무것도 안 하고 돌아가기
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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    # 슬롯 존재 / 소속 키오스크 확인
    slot = await db.get(VendingSlot, slot_id)
    if not slot or slot.kiosk_id != kiosk_id:
        return RedirectResponse(f"/kiosks/{kiosk_id}", status_code=303)

    # 슬롯에 매핑된 상품 레코드 삭제
    result = await db.execute(
        select(VendingSlotProduct).where(VendingSlotProduct.slot_id == slot_id)
    )
    vsp = result.scalar_one_or_none()

    if vsp:
        await db.delete(vsp)

    # 옵션: 슬롯 자체 용량/재고 관련 값 초기화
    slot.max_capacity = 0

    await db.commit()

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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    # 슬롯 존재 여부 확인 + max_capacity 업데이트
    slot_stmt = select(VendingSlot).where(VendingSlot.id == slot_id)
    slot_result = await db.execute(slot_stmt)
    slot = slot_result.scalar_one_or_none()

    if not slot:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 슬롯입니다."},
            status_code=404,
        )

    slot.max_capacity = max_capacity
    slot.updated_at = datetime.utcnow()

    # 슬롯-상품 링크 upsert
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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 키오스크입니다."},
            status_code=404,
        )

    # R2 업로드 (prefix는 자유롭게)
    image_url = await upload_image_to_r2(file, prefix=f"kiosk/{kiosk.code}/screensaver")

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
    if current_user.role != 1:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "권한이 없습니다."},
            status_code=403,
        )

    kiosk = await kiosk_service.get_by_id(db, kiosk_id)
    if not kiosk:
        return templates.TemplateResponse(
            "forbidden.html",
            {"request": request, "message": "존재하지 않는 키오스크입니다."},
            status_code=404,
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

    return RedirectResponse(f"/kiosks/{kiosk_id}?mode=view", status_code=303)