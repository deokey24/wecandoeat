# app/back/services/kiosk_product_i18n.py
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# <br>, <Br>, <br/>, <br /> 등 모든 변형을 공백 1칸으로 치환
_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)

def sanitize_text(value: Optional[str]) -> str:
    """
    - None -> ""
    - <br> 류 태그를 공백 1칸으로 치환
    - 연속 공백 정리
    """
    if not value:
        return ""
    s = value.strip()
    s = _BR_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass(frozen=True)
class I18nName:
    en: str
    zh: str
    ja: str


_I18N_JSON_SCHEMA = {
    "name": "product_name_i18n",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "en": {"type": "string"},
            "zh": {"type": "string"},
            "ja": {"type": "string"},
        },
        "required": ["en", "zh", "ja"],
    },
}


async def translate_name_i18n(
    client: AsyncOpenAI,
    source_name: str,
    *,
    model: str = "gpt-4o-mini",
) -> I18nName:
    """
    OpenAI를 통해 상품명 번역(en/zh/ja). (모듈화: 버튼/배치 모두 재사용)
    입력은 sanitize_text로 정규화 후 사용.
    출력도 sanitize_text로 한 번 더 정리.
    """
    cleaned = sanitize_text(source_name)
    if not cleaned:
        return I18nName(en="", zh="", ja="")

    resp = await client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "Translate product names into English, Simplified Chinese, and Japanese.\n"
                    "Rules:\n"
                    "- Keep brand names, model numbers, sizes, and units unchanged.\n"
                    "- Do not add marketing words or extra info.\n"
                    "- Be concise and natural.\n"
                    "- Output JSON only with keys: en, zh, ja."
                ),
            },
            {"role": "user", "content": f"Product name: {cleaned}"},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "product_name_i18n",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "en": {"type": "string"},
                        "zh": {"type": "string"},
                        "ja": {"type": "string"},
                    },
                    "required": ["en", "zh", "ja"],
                },
            }
        }
        ,
        temperature=0.2,
    )

    data = json.loads(resp.output_text)
    return I18nName(
        en=sanitize_text(data.get("en")),
        zh=sanitize_text(data.get("zh")),
        ja=sanitize_text(data.get("ja")),
    )


async def fill_kiosk_product_i18n(
    session: AsyncSession,
    client: AsyncOpenAI,
    kiosk_product_id: int,
    *,
    force: bool = False,
    model: str = "gpt-4o-mini",
) -> Optional[I18nName]:
    """
    단일 kiosk_products 레코드에 대해:
    - name 컬럼 자체도 <br> -> 공백으로 정규화하여 저장
    - name_en/name_zh/name_ja 채움(기본은 빈 필드만, force면 덮어씀)
    - name_i18n_status, name_i18n_updated_at 업데이트

    Returns:
      - 번역/업데이트가 수행되면 I18nName
      - 스킵되면 None
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id, name, name_en, name_zh, name_ja
                FROM kiosk_products
                WHERE id = :id
                """
            ),
            {"id": kiosk_product_id},
        )
    ).mappings().first()

    if not row:
        return None

    # 1) name 정규화 (DB에 저장)
    raw_name = row.get("name") or ""
    clean_name = sanitize_text(raw_name)

    # name이 비어있으면 번역 불가
    if not clean_name:
        # name이 "<br>" 같은 것 때문에 비어지는 케이스면 정규화만 해두고 상태 실패로 마킹할지 선택 가능
        # 여기서는 정규화만 하고 종료
        if raw_name != clean_name:
            await session.execute(
                text("UPDATE kiosk_products SET name = :name WHERE id = :id"),
                {"id": kiosk_product_id, "name": clean_name},
            )
            await session.commit()
        return None

    # 2) 이미 번역이 다 채워져 있으면 스킵 (force가 아니면)
    existing_en = (row.get("name_en") or "").strip()
    existing_zh = (row.get("name_zh") or "").strip()
    existing_ja = (row.get("name_ja") or "").strip()

    if not force and existing_en and existing_zh and existing_ja:
        # name 정규화만 필요하면 반영
        if raw_name != clean_name:
            await session.execute(
                text("UPDATE kiosk_products SET name = :name WHERE id = :id"),
                {"id": kiosk_product_id, "name": clean_name},
            )
            # 상태는 굳이 바꾸지 않는 편이 안전(운영 정책에 따라 변경 가능)
            await session.commit()
        return None

    # 3) 번역 수행 (입력은 정규화된 name)
    now = datetime.now(timezone.utc)

    try:
        # 번역 시작 상태
        await session.execute(
            text(
                """
                UPDATE kiosk_products
                SET name = :name,
                    name_i18n_status = :status,
                    name_i18n_updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": kiosk_product_id,
                "name": clean_name,
                "status": "pending",
                "updated_at": now,
            },
        )
        await session.commit()

        out = await translate_name_i18n(client, clean_name, model=model)

        # 4) 업데이트 값 구성 (force=False면 빈 필드만 채우기)
        new_en = out.en if (force or not existing_en) else existing_en
        new_zh = out.zh if (force or not existing_zh) else existing_zh
        new_ja = out.ja if (force or not existing_ja) else existing_ja

        await session.execute(
            text(
                """
                UPDATE kiosk_products
                SET name = :name,
                    name_en = :en,
                    name_zh = :zh,
                    name_ja = :ja,
                    name_i18n_status = :status,
                    name_i18n_updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": kiosk_product_id,
                "name": clean_name,
                "en": new_en,
                "zh": new_zh,
                "ja": new_ja,
                "status": "success",
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await session.commit()
        return I18nName(en=new_en or "", zh=new_zh or "", ja=new_ja or "")

    except Exception:
        await session.rollback()
        # 실패 상태 업데이트(가능한 경우)
        try:
            await session.execute(
                text(
                    """
                    UPDATE kiosk_products
                    SET name = :name,
                        name_i18n_status = :status,
                        name_i18n_updated_at = :updated_at
                    WHERE id = :id
                    """
                ),
                {
                    "id": kiosk_product_id,
                    "name": clean_name,
                    "status": "failed",
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            await session.commit()
        except Exception:
            await session.rollback()
        raise
