# scripts/insert_products.py

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.back.core.db import async_session_maker
from app.back.models.product import ProductCreate
from app.back.services import product_service


JSON_PATH = Path("products.json")  # JSON 파일 경로


async def bulk_insert():
    # JSON 로드
    items = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    async with async_session_maker() as db:  # type: AsyncSession
        for idx, item in enumerate(items, start=1):
            data = ProductCreate(
                name=item["상품명"].strip(),
                category=item.get("카테고리"),
                price=int(item["판매가"]),
                is_adult_only=True,  # 🔥 기본 성인 상품
                image_url=item.get("상품이미지url"),
                detail_url=item.get("상세이미지url"),
                image_object_key=None,
                detail_object_key=None,
                description=None,
            )

            await product_service.create_product(db, data)
            print(f"[{idx}] 등록 완료: {data.name}")

    print("✅ 전체 상품 등록 완료")


if __name__ == "__main__":
    asyncio.run(bulk_insert())
