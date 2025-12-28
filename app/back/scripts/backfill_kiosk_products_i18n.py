# scripts/backfill_kiosk_products_i18n.py
import asyncio
import os
import logging
from typing import Any, Dict, List
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
from sqlalchemy import text

from app.back.core.db import AsyncSessionLocal
from app.back.services.kiosk_product_i18n import fill_kiosk_product_i18n


# =========================
# Logging 설정
# =========================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(
    LOG_DIR,
    f"backfill_kiosk_products_i18n_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[
        logging.StreamHandler(),                 # 콘솔
        logging.FileHandler(log_file, encoding="utf-8"),  # 파일
    ],
)

logger = logging.getLogger(__name__)


async def backfill_all(
    *,
    limit_total: int = 1_000_000,
    page_size: int = 100,
    sleep_s: float = 0.25,
    force: bool = False,
    model: str = "gpt-4o-mini",
) -> None:
    """
    kiosk_products 전체를 대상으로 i18n 필드 채우기 + 로그 출력
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is missing in environment variables.")

    client = AsyncOpenAI(api_key=api_key)

    processed = 0
    success = 0
    failed: List[Dict[str, Any]] = []
    last_id = 0

    logger.info("=== Kiosk Product i18n Backfill START ===")
    logger.info(
        "options: force=%s, page_size=%s, sleep_s=%s, model=%s",
        force, page_size, sleep_s, model
    )

    async with AsyncSessionLocal() as session:
        while processed < limit_total:
            ids = (
                await session.execute(
                    text(
                        """
                        SELECT id
                        FROM kiosk_products
                        WHERE id > :last_id
                          AND (
                                COALESCE(name_en, '') = ''
                             OR COALESCE(name_zh, '') = ''
                             OR COALESCE(name_ja, '') = ''
                          )
                        ORDER BY id
                        LIMIT :limit
                        """
                    ),
                    {"last_id": last_id, "limit": page_size},
                )
            ).scalars().all()

            if not ids:
                break

            for kid in ids:
                last_id = kid
                processed += 1

                try:
                    result = await fill_kiosk_product_i18n(
                        session=session,
                        client=client,
                        kiosk_product_id=kid,
                        force=force,
                        model=model,
                    )

                    if result:
                        success += 1
                        logger.info(
                            "[%d/%d] SUCCESS | kiosk_product_id=%s | en='%s'",
                            processed, limit_total, kid, result.en
                        )
                    else:
                        logger.warning(
                            "[%d/%d] SKIP | kiosk_product_id=%s (already filled or empty)",
                            processed, limit_total, kid
                        )

                except Exception as e:
                    await session.rollback()
                    failed.append({"id": kid, "error": str(e)})
                    logger.error(
                        "[%d/%d] FAIL | kiosk_product_id=%s | error=%s",
                        processed, limit_total, kid, e,
                        exc_info=True
                    )

                # 주기적으로 진행률 요약
                if processed % 20 == 0:
                    logger.info(
                        "Progress: processed=%d, success=%d, failed=%d",
                        processed, success, len(failed)
                    )

                await asyncio.sleep(sleep_s)

    logger.info("=== Kiosk Product i18n Backfill END ===")
    logger.info(
        "Result Summary: processed=%d, success=%d, failed=%d",
        processed, success, len(failed)
    )

    if failed:
        logger.info("Failed samples (up to 10):")
        for item in failed[:10]:
            logger.info("  id=%s error=%s", item["id"], item["error"])

    logger.info("Log file saved to: %s", log_file)


if __name__ == "__main__":
    asyncio.run(
        backfill_all(
            limit_total=1_000_000,
            page_size=50,     # 처음엔 20~50 권장
            sleep_s=20,
            force=False,
            model="gpt-4o-mini",
        )
    )
